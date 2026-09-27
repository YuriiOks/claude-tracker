"""Parse a Claude Code JSONL transcript into LiveEvents and a SessionSummary.

Real line types observed in ~/.claude/projects/**/*.jsonl:
  user, assistant, system, attachment, progress, queue-operation,
  permission-mode, last-prompt, custom-title, agent-name, file-history-snapshot

Approach: stream-parse line by line, tolerate unknown types (log + skip), never
raise on malformed input. The parser is the bottleneck — keep it linear in lines.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)


class ModelPrice(NamedTuple):
    """USD per million tokens, plus the cache-read (hit) multiplier applied
    against `input` -- most models bill a cache-read hit at 0.1x the base
    input price, but a few current-generation models get a steeper discount
    (see the source cited below), so it's per-model rather than a global
    constant.
    """

    input: float
    output: float
    cache_read_mult: float = 0.1


# USD per million tokens, keyed by (family, version). Cache-WRITE multipliers
# (5m-TTL = 1.25x input, 1h-TTL = 2.0x input) are uniform across every model
# in the verified table below and are applied directly in the cost formula
# rather than stored per-entry.
#
# Verified live against https://docs.anthropic.com/en/docs/about-claude/pricing
# (fetched 2026-09-27) for every entry annotated "verified 2026-09-27" below.
# Unannotated entries (older Claude 3.x tiers) are carried over from before
# this pass -- they no longer appear on the current pricing page (likely
# retired/legacy-only) and are NOT present in any of the owner's real
# transcripts, so they're left as-is rather than guessed at: UNVERIFIED.
_PRICING: dict[tuple[str, str], ModelPrice] = {
    # --- verified 2026-09-27 (already matched the prior static entry, no change) ---
    ("opus", "4-1"): ModelPrice(15.0, 75.0),
    ("opus", "4"): ModelPrice(15.0, 75.0),
    ("sonnet", "4-5"): ModelPrice(3.0, 15.0),
    ("sonnet", "4"): ModelPrice(3.0, 15.0),
    ("haiku", "3-5"): ModelPrice(0.80, 4.0),
    # --- verified 2026-09-27 (corrects prior wrong/guessed entries) ---
    ("opus", "4-8"): ModelPrice(5.0, 25.0),  # was wrongly (15,75) -- copy of Opus 4's rate
    ("opus", "4-7"): ModelPrice(5.0, 25.0),  # was wrongly (15,75)
    ("opus", "4-6"): ModelPrice(5.0, 25.0),  # new -- previously fell through to family default
    ("opus", "4-5"): ModelPrice(5.0, 25.0),  # was wrongly (15,75)
    ("opus", "5"): ModelPrice(5.0, 25.0),  # new -- 2nd-highest-volume real model id
    ("opus", "5-5"): ModelPrice(4.0, 20.0, cache_read_mult=0.05),  # new; discounted cache-read
    ("sonnet", "5"): ModelPrice(2.0, 10.0),  # was wrongly (3,15) -- highest-volume real model id
    ("sonnet", "4-6"): ModelPrice(3.0, 15.0),  # new exact entry (was already correct via family default)
    ("haiku", "4-5"): ModelPrice(1.0, 5.0),  # was wrongly (0.80,4.0) -- a copy-paste of Haiku 3.5's rate
    ("fable", "5"): ModelPrice(10.0, 50.0),  # was a conservative Opus-tier guess (15,75); now confirmed
    ("fable", "5-1"): ModelPrice(10.0, 50.0, cache_read_mult=0.025),  # new; discounted cache-read
    ("mythos", "5"): ModelPrice(10.0, 50.0),  # was a conservative Opus-tier guess (15,75); now confirmed
    ("mythos", "5-1"): ModelPrice(10.0, 50.0, cache_read_mult=0.025),  # new; discounted cache-read
    # --- UNVERIFIED: not present on the current pricing page, not present in
    # any real transcript in this corpus (grep confirmed zero matches for
    # opus-3*/sonnet-3*/haiku-3 as of 2026-09-27) -- carried over rather than
    # guessed at.
    ("opus", "3-5"): ModelPrice(15.0, 75.0),
    ("opus", "3"): ModelPrice(15.0, 75.0),
    ("sonnet", "3-7"): ModelPrice(3.0, 15.0),
    ("sonnet", "3-5"): ModelPrice(3.0, 15.0),
    ("sonnet", "3"): ModelPrice(3.0, 15.0),
    ("haiku", "3"): ModelPrice(0.25, 1.25),
}
# Fallback for a recognized family whose specific version is not yet listed
# above (e.g. a brand-new dated release) -- keeps the right cost tier instead
# of silently dropping to the global default. Verified 2026-09-27 against the
# same pricing page as the table above.
_FAMILY_DEFAULT: dict[str, ModelPrice] = {
    "opus": ModelPrice(5.0, 25.0),
    "sonnet": ModelPrice(2.0, 10.0),
    "haiku": ModelPrice(1.0, 5.0),
    "fable": ModelPrice(10.0, 50.0, cache_read_mult=0.025),
    "mythos": ModelPrice(10.0, 50.0, cache_read_mult=0.025),
}
_DEFAULT_PRICE = ModelPrice(3.0, 15.0)  # Sonnet-tier -- see _price()'s warning-on-fallback below

# Populated once per distinct unmatched model id so the same unrecognized
# model doesn't spam the log on every turn/tick -- see _price().
_warned_unknown_models: set[str] = set()


def _warn_unknown_model_once(model: str | None) -> None:
    key = model or "<missing>"
    if key in _warned_unknown_models:
        return
    _warned_unknown_models.add(key)
    logger.warning(
        "unrecognized model id %r -- pricing at Sonnet-tier defaults "
        "($%.2f/$%.2f per MTok in/out); add a _PRICING entry once real "
        "rates are confirmed (see jsonl_parser.py's _PRICING table)",
        key,
        _DEFAULT_PRICE.input,
        _DEFAULT_PRICE.output,
    )


@dataclass
class ParsedEvent:
    ts: datetime
    repo: str
    kind: str  # agent_start | tool | delegate | skill | permission | command
    payload: dict = field(default_factory=dict)
    seq: int | None = None  # Hub-assigned monotonic id, set only for live-broadcast events


@dataclass
class SessionSummary:
    session_id: str
    repo: str
    started_at: datetime
    last_event_at: datetime
    agent: str | None = None
    task: str | None = None
    status: str = "completed"
    tokens: int = 0
    cost: float = 0.0
    edits: int = 0
    file_path: str = ""
    file_mtime: float = 0.0
    hourly_tokens: dict = field(default_factory=dict)
    # message_id -> (turn_tokens, turn_cost, hour_key). One entry per unique
    # assistant message.id counted into tokens/cost/hourly_tokens above.
    # Used by ingest.py to reconcile ownership when the same message.id
    # shows up in more than one file (resumed sessions, broadcast system
    # messages) -- see app.models.message_ledger. Messages with no id
    # (legacy format) are never added here since they can't be deduped
    # across files; they're always folded straight into the totals above.
    message_usage: dict = field(default_factory=dict)


def _ts(obj: dict) -> datetime | None:
    raw = obj.get("timestamp")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _repo_from_cwd(cwd: str | None, repo_paths: list[Path]) -> str:
    if not cwd:
        return "unknown"
    # Translate host paths → container paths so docker users get matches.
    from app.config import get_settings
    cwd_p = get_settings().translate_host_path(cwd)
    for rp in repo_paths:
        try:
            cwd_p.relative_to(rp)
            return rp.name
        except ValueError:
            continue
    # cwd is not in a registered repo. Walk up to find the nearest .git
    # ancestor and use its folder name — this is the project name, not the
    # leaf folder where claude happened to be invoked (e.g. "frontend"
    # inside a project called "my-app" → returns "my-app").
    try:
        cur = cwd_p if cwd_p.is_dir() else cwd_p.parent
        for _ in range(20):
            if (cur / ".git").is_dir():
                return cur.name
            if cur == cur.parent:
                break
            cur = cur.parent
    except OSError:
        pass
    # Last resort: leaf folder name.
    return Path(cwd).name


def _content_text(content) -> str:  # noqa: ANN001
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                return str(c.get("text", ""))
            if isinstance(c, dict) and isinstance(c.get("content"), str):
                return c["content"]
    return ""


# Matches "claude-{family}-{version}" (current naming, e.g. "claude-opus-4-5")
# and legacy "claude-{version}-{family}" (e.g. "claude-3-opus-20240229" or
# "claude-3-5-sonnet-20241022") -- the family word can appear before or after
# the version digits, so we search for it instead of assuming an order.
_MODEL_RE = re.compile(
    r"claude-(?:(?P<pre>\d[\d-]*)-)?(?P<family>opus|sonnet|haiku|fable|mythos)(?:-(?P<post>\d[\d-]*))?"
)


def _price(model: str | None) -> ModelPrice:
    if not model:
        _warn_unknown_model_once(model)
        return _DEFAULT_PRICE
    m = model.lower()
    match = _MODEL_RE.search(m)
    if not match:
        _warn_unknown_model_once(model)
        return _DEFAULT_PRICE
    family = match.group("family")
    version_raw = match.group("pre") or match.group("post") or ""
    # Strip a trailing release-date suffix (e.g. "-20251101") -- dates are
    # 8-digit segments, real version numbers are 1-2 digits.
    version = "-".join(seg for seg in version_raw.split("-") if seg and len(seg) < 6)
    return _PRICING.get((family, version)) or _FAMILY_DEFAULT.get(family, _DEFAULT_PRICE)


_EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


@dataclass
class _ParseState:
    """Mutable accumulator threaded through `_process_line` by both the
    full-file parser (`parse_jsonl`) and the incremental delta parser
    (`parse_jsonl_incremental`). For a full parse it starts empty; for an
    incremental parse it starts pre-seeded with whatever this file's prior
    increment(s) already established (session_id, repo, agent_name,
    task_text, seen_message_ids) so a growing file's tail reads exactly the
    same as if the whole file had been parsed in one pass.
    """

    session_id: str | None = None
    repo: str = "unknown"
    started_at: datetime | None = None
    last_ts: datetime | None = None
    agent_name: str | None = None
    task_text: str | None = None
    tokens: int = 0
    cost: float = 0.0
    edits: int = 0
    model_seen: str | None = None
    seen_message_ids: set[str] = field(default_factory=set)
    hourly_tokens: dict = field(default_factory=dict)
    message_usage: dict = field(default_factory=dict)


def _process_line(
    raw: str, repo_paths: list[Path], state: _ParseState, events: list[ParsedEvent]
) -> None:
    """Parse one JSONL line, mutating `state` in place and appending any
    ParsedEvent(s) it produces. Shared by the full and incremental parsers
    so a line means exactly the same thing regardless of which one reads it.
    """
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(obj, dict):
        # A valid JSON value that is not a record (e.g. a bare number) --
        # never a transcript event; skip it instead of crashing the walk.
        return

    t = obj.get("type", "")
    state.session_id = state.session_id or obj.get("sessionId")
    cwd = obj.get("cwd")
    if cwd and state.repo == "unknown":
        state.repo = _repo_from_cwd(cwd, repo_paths)

    ts = _ts(obj)
    if ts is not None:
        if state.started_at is None:
            state.started_at = ts
        state.last_ts = ts

    if t == "agent-name":
        state.agent_name = obj.get("agentName") or state.agent_name

    elif t == "user":
        msg = obj.get("message", {}) or {}
        text = _content_text(msg.get("content", "")) or ""
        if state.task_text is None and text and not text.startswith("[system"):
            state.task_text = text[:160]
        if text.startswith("/") and ts is not None:
            cmd = text.split()[0]
            events.append(ParsedEvent(ts, state.repo, "command", {"cmd": cmd, "msg": text[:140]}))

    elif t == "assistant":
        msg = obj.get("message", {}) or {}
        state.model_seen = msg.get("model") or state.model_seen
        msg_id = msg.get("id")
        usage = msg.get("usage", {}) or {}
        # Claude Code splits one logical assistant turn (thinking / text /
        # each tool_use block) across multiple JSONL lines that all share
        # the same message.id and all repeat the SAME consolidated,
        # non-delta usage object. Only fold usage in once per unique
        # message.id -- otherwise tokens/cost get summed once per split
        # line (measured ~7x inflation vs. a deduped baseline on a real
        # transcript). A set (not just "differs from the last seen id")
        # catches non-consecutive repeats too. Lines with no id (older
        # format) always count, since we cannot tell whether they
        # duplicate a prior turn, and can't be cross-file deduped either.
        # For an incremental parse, `state.seen_message_ids` is pre-seeded
        # with every id this same file already counted in a PRIOR
        # increment (from message_ledger) -- this is what stops a message
        # whose split lines straddle the increment boundary from being
        # double-counted when its later half is read on the next tick.
        is_new_turn = msg_id is None or msg_id not in state.seen_message_ids
        if msg_id is not None:
            state.seen_message_ids.add(msg_id)
        if is_new_turn:
            in_tok = int(usage.get("input_tokens", 0) or 0)
            out_tok = int(usage.get("output_tokens", 0) or 0)
            cache_write = int(usage.get("cache_creation_input_tokens", 0) or 0)
            cache_read = int(usage.get("cache_read_input_tokens", 0) or 0)
            # Headline tokens = generation work (input + output + cache_creation).
            # cache_read_input_tokens is intentionally excluded from the TOKEN
            # count (though it IS billed, see cost below): long-lived sessions
            # can re-read the same 80k-token cached system prompt thousands of
            # times -- a single 8h session can easily accumulate 670M cache_read
            # tokens against just 1.3M output, inflating the headline "tokens"
            # figure by ~100x in a way that does not reflect actual generation
            # effort. This keeps the dashboard's token story consistent with
            # Claude Code's own definition (input + output + cache writes) while
            # still charging real dollars for cache reads in `cost` below.
            turn_tokens = in_tok + out_tok + cache_write
            price = _price(state.model_seen)
            turn_cost = (in_tok / 1_000_000) * price.input
            turn_cost += (out_tok / 1_000_000) * price.output
            # Cache writes: Anthropic bills the 5-minute-TTL tier at 1.25x
            # input and the 1-hour-TTL tier at 2x input -- real usage is
            # overwhelmingly 1h-TTL, so blending everything at the flat 1.25x
            # rate understated cost. Split by TTL when the API tells us
            # (usage.cache_creation.{ephemeral_1h,ephemeral_5m}_input_tokens),
            # falling back to the flat 1.25x-of-the-summed-total only for the
            # older/rarer response shape that omits the sub-object entirely.
            cache_detail = usage.get("cache_creation")
            if isinstance(cache_detail, dict):
                cache_1h = int(cache_detail.get("ephemeral_1h_input_tokens", 0) or 0)
                cache_5m = int(cache_detail.get("ephemeral_5m_input_tokens", 0) or 0)
                turn_cost += (cache_1h / 1_000_000) * price.input * 2.0
                turn_cost += (cache_5m / 1_000_000) * price.input * 1.25
            else:
                turn_cost += (cache_write / 1_000_000) * price.input * 1.25
            # Cache reads are billed too (at a model-specific fraction of the
            # input rate -- see ModelPrice.cache_read_mult) even though they're
            # excluded from the token headline above: a dashboard cost figure
            # that ignores them is a floor, not real spend, on any session that
            # uses prompt caching (effectively all Claude Code sessions).
            turn_cost += (cache_read / 1_000_000) * price.input * price.cache_read_mult
            state.tokens += turn_tokens
            state.cost += turn_cost
            hour_key = None
            if ts is not None and turn_tokens > 0:
                hour_key = ts.replace(minute=0, second=0, microsecond=0)
                state.hourly_tokens[hour_key] = state.hourly_tokens.get(hour_key, 0) + turn_tokens
            if msg_id is not None:
                state.message_usage[msg_id] = (turn_tokens, turn_cost, hour_key)

        content = msg.get("content", [])
        if isinstance(content, list) and ts is not None:
            for c in content:
                if not isinstance(c, dict) or c.get("type") != "tool_use":
                    continue
                tool = c.get("name", "")
                ti = c.get("input", {}) or {}
                if tool in _EDIT_TOOLS:
                    state.edits += 1
                if tool in ("Task", "Agent"):
                    target = ti.get("subagent_type") or ti.get("description", "")
                    events.append(
                        ParsedEvent(
                            ts,
                            state.repo,
                            "delegate",
                            {
                                "from": state.agent_name or "main",
                                "to": str(target),
                                "msg": str(ti.get("prompt", ""))[:140],
                            },
                        )
                    )
                elif tool == "Skill":
                    skill_name = (
                        ti.get("skill")
                        or ti.get("path")
                        or ti.get("name")
                        or "skill"
                    )
                    events.append(
                        ParsedEvent(ts, state.repo, "skill", {"skill": str(skill_name)})
                    )
                else:
                    target = (
                        ti.get("file_path")
                        or ti.get("path")
                        or ti.get("command")
                        or ti.get("pattern")
                        or ""
                    )
                    events.append(
                        ParsedEvent(
                            ts,
                            state.repo,
                            "tool",
                            {"tool": tool, "target": str(target)[:200]},
                        )
                    )

    elif t == "system":
        sub = obj.get("subtype", "")
        if "permission" in sub.lower() and ts is not None:
            events.append(
                ParsedEvent(
                    ts,
                    state.repo,
                    "permission",
                    {
                        "level": obj.get("level", "ask"),
                        "action": obj.get("action", ""),
                        "granted": bool(obj.get("granted", False)),
                    },
                )
            )

    # Unknown types are silently dropped.


def parse_jsonl(
    path: Path, repo_paths: list[Path]
) -> tuple[SessionSummary | None, list[ParsedEvent]]:
    """Stream-parse one JSONL file from byte 0; return (summary, events).

    Returns (None, []) if the file is empty or unreadable. Full-file totals
    -- for a growing file, prefer `parse_jsonl_incremental` so an ingest
    tick doesn't re-read+re-parse bytes it already accounted for.
    """
    if not path.is_file():
        return None, []

    events: list[ParsedEvent] = []
    state = _ParseState()

    try:
        fh = path.open("r", encoding="utf-8", errors="replace")
    except OSError as e:
        logger.warning("cannot open %s: %s", path, e)
        return None, []

    with fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            _process_line(raw, repo_paths, state, events)

    if state.session_id is None or state.started_at is None or state.last_ts is None:
        return None, []

    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0

    summary = SessionSummary(
        session_id=state.session_id,
        repo=state.repo,
        started_at=state.started_at,
        last_event_at=state.last_ts,
        agent=state.agent_name,
        task=state.task_text,
        status="completed",
        tokens=state.tokens,
        cost=round(state.cost, 4),
        edits=state.edits,
        file_path=str(path),
        file_mtime=mtime,
    )
    summary.hourly_tokens = state.hourly_tokens
    summary.message_usage = state.message_usage
    return summary, events


@dataclass
class IncrementalParseResult:
    """Result of parsing only the bytes appended to a file since a prior
    offset. `summary` (when not None) holds ONLY this increment's DELTA --
    tokens/cost/edits/hourly_tokens/message_usage are amounts to ADD to the
    stored row, never the file's running total. `repo`/`agent_name`/
    `task_text`/`session_id` are the (possibly newly-resolved, possibly
    unchanged) continuation state the caller must persist for the next
    increment even when `summary` is None (e.g. a delta that only contained
    a bare `agent-name` record still needs its `agent_name` carried
    forward).
    """

    new_offset: int
    summary: SessionSummary | None
    events: list[ParsedEvent] = field(default_factory=list)
    last_ts: datetime | None = None
    repo: str = "unknown"
    agent_name: str | None = None
    task_text: str | None = None
    session_id: str | None = None


def parse_jsonl_incremental(
    path: Path,
    repo_paths: list[Path],
    start_offset: int,
    seen_message_ids: set[str],
    *,
    session_id: str | None = None,
    repo: str = "unknown",
    agent_name: str | None = None,
    task_text: str | None = None,
) -> IncrementalParseResult:
    """Parse only the bytes appended since `start_offset`.

    Mirrors live_stream._tail_new_lines's byte-offset discipline: only
    advances past the LAST complete newline in the new bytes, so a trailing
    partial line (a concurrent writer mid-flush) is left unread -- the
    caller must NOT advance its stored offset past `new_offset` and must
    retry from the same `start_offset` on the next tick.

    `seen_message_ids` seeds the in-file split-turn dedup with every
    message id this exact file has already fully counted in a PRIOR
    increment (the caller looks this up from message_ledger, scoped to this
    file's own path) -- without this seed, a message whose repeated
    usage-carrying JSONL lines straddle the previous increment's offset
    boundary would have its tokens/cost counted a second time when the
    later split line is seen in this increment.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return IncrementalParseResult(start_offset, None, repo=repo, agent_name=agent_name,
                                       task_text=task_text, session_id=session_id)
    if size <= start_offset:
        return IncrementalParseResult(start_offset, None, repo=repo, agent_name=agent_name,
                                       task_text=task_text, session_id=session_id)

    try:
        with path.open("rb") as fh:
            fh.seek(start_offset)
            chunk = fh.read()
    except OSError:
        return IncrementalParseResult(start_offset, None, repo=repo, agent_name=agent_name,
                                       task_text=task_text, session_id=session_id)

    last_nl = chunk.rfind(b"\n")
    if last_nl == -1:
        # No complete line yet -- leave the offset untouched, exactly like
        # live_stream._tail_new_lines.
        return IncrementalParseResult(start_offset, None, repo=repo, agent_name=agent_name,
                                       task_text=task_text, session_id=session_id)

    complete = chunk[: last_nl + 1]
    new_offset = start_offset + last_nl + 1
    text = complete.decode("utf-8", errors="replace")

    events: list[ParsedEvent] = []
    state = _ParseState(
        session_id=session_id,
        repo=repo,
        agent_name=agent_name,
        task_text=task_text,
        seen_message_ids=set(seen_message_ids),
    )
    # JSONL records are separated by "\n" ONLY. str.splitlines() also breaks
    # on U+2028/U+2029/U+0085/\x0c/etc., which are legal inside JSON strings
    # and do occur in real transcripts -- splitting on them corrupts records
    # (fragments can even decode to bare ints).
    for raw in text.split("\n"):
        raw = raw.strip()
        if not raw:
            continue
        _process_line(raw, repo_paths, state, events)

    if state.session_id is None or state.last_ts is None:
        # Nothing usable in this increment (e.g. only a bare agent-name
        # record, or blank lines) -- still report the advanced offset and
        # whatever continuation state DID change so the caller can persist
        # it, but there is no numeric delta to merge.
        return IncrementalParseResult(
            new_offset, None, events, last_ts=state.last_ts, repo=state.repo,
            agent_name=state.agent_name, task_text=state.task_text, session_id=state.session_id,
        )

    delta = SessionSummary(
        session_id=state.session_id,
        repo=state.repo,
        started_at=state.started_at or state.last_ts,
        last_event_at=state.last_ts,
        agent=state.agent_name,
        task=state.task_text,
        tokens=state.tokens,
        cost=round(state.cost, 4),
        edits=state.edits,
        file_path=str(path),
        file_mtime=0.0,
    )
    delta.hourly_tokens = state.hourly_tokens
    delta.message_usage = state.message_usage
    return IncrementalParseResult(
        new_offset, delta, events, last_ts=state.last_ts, repo=state.repo,
        agent_name=state.agent_name, task_text=state.task_text, session_id=state.session_id,
    )


def iter_jsonl_files(projects_dir: Path) -> Iterator[Path]:
    if not projects_dir.is_dir():
        return iter(())
    return projects_dir.rglob("*.jsonl")
