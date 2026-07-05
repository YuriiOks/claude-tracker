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

logger = logging.getLogger(__name__)

# Rough USD per million tokens (input, output), keyed by (family, version).
# NOTE: this is a static table -- it needs periodic updating against real
# Anthropic pricing (see anthropic.com/pricing). Entries for the "claude-5"
# tier (Fable 5 / Mythos 5) are a conservative assumption -- priced at the
# Opus tier pending official published rates -- not authoritative figures.
_PRICING: dict[tuple[str, str], tuple[float, float]] = {
    ("opus", "4-7"): (15.0, 75.0),
    ("opus", "4-5"): (15.0, 75.0),
    ("opus", "4-1"): (15.0, 75.0),
    ("opus", "4-8"): (15.0, 75.0),
    ("opus", "4"): (15.0, 75.0),
    ("opus", "3-5"): (15.0, 75.0),
    ("opus", "3"): (15.0, 75.0),
    ("sonnet", "4-5"): (3.0, 15.0),
    ("sonnet", "4"): (3.0, 15.0),
    ("sonnet", "3-7"): (3.0, 15.0),
    ("sonnet", "3-5"): (3.0, 15.0),
    ("sonnet", "3"): (3.0, 15.0),
    ("sonnet", "5"): (3.0, 15.0),
    ("haiku", "4-5"): (0.80, 4.0),
    ("haiku", "3-5"): (0.80, 4.0),
    ("haiku", "3"): (0.25, 1.25),
    # Claude 5 family -- see NOTE above.
    ("fable", "5"): (15.0, 75.0),
    ("mythos", "5"): (15.0, 75.0),
}
# Fallback for a recognized family whose specific version is not yet listed
# above (e.g. a brand-new dated release) -- keeps the right cost tier instead
# of silently dropping to the global default.
_FAMILY_DEFAULT: dict[str, tuple[float, float]] = {
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (0.80, 4.0),
    "fable": (15.0, 75.0),
    "mythos": (15.0, 75.0),
}
_DEFAULT_PRICE = (3.0, 15.0)


@dataclass
class ParsedEvent:
    ts: datetime
    repo: str
    kind: str  # agent_start | tool | delegate | skill | permission | command
    payload: dict = field(default_factory=dict)


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


def _price(model: str | None) -> tuple[float, float]:
    if not model:
        return _DEFAULT_PRICE
    m = model.lower()
    match = _MODEL_RE.search(m)
    if not match:
        return _DEFAULT_PRICE
    family = match.group("family")
    version_raw = match.group("pre") or match.group("post") or ""
    # Strip a trailing release-date suffix (e.g. "-20251101") -- dates are
    # 8-digit segments, real version numbers are 1-2 digits.
    version = "-".join(seg for seg in version_raw.split("-") if seg and len(seg) < 6)
    return _PRICING.get((family, version)) or _FAMILY_DEFAULT.get(family, _DEFAULT_PRICE)


_EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def parse_jsonl(
    path: Path, repo_paths: list[Path]
) -> tuple[SessionSummary | None, list[ParsedEvent]]:
    """Stream-parse one JSONL file; return (summary, events).

    Returns (None, []) if the file is empty or unreadable.
    """
    if not path.is_file():
        return None, []

    events: list[ParsedEvent] = []
    session_id: str | None = None
    repo: str = "unknown"
    started_at: datetime | None = None
    last_ts: datetime | None = None
    agent_name: str | None = None
    task_text: str | None = None
    tokens = 0
    cost = 0.0
    edits = 0
    model_seen: str | None = None
    last_assistant_msg_id: str | None = None
    hourly_tokens: dict = {}

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
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue

            t = obj.get("type", "")
            session_id = session_id or obj.get("sessionId")
            cwd = obj.get("cwd")
            if cwd and repo == "unknown":
                repo = _repo_from_cwd(cwd, repo_paths)

            ts = _ts(obj)
            if ts is not None:
                if started_at is None:
                    started_at = ts
                last_ts = ts

            if t == "agent-name":
                agent_name = obj.get("agentName") or agent_name

            elif t == "user":
                msg = obj.get("message", {}) or {}
                text = _content_text(msg.get("content", "")) or ""
                if task_text is None and text and not text.startswith("[system"):
                    task_text = text[:160]
                if text.startswith("/") and ts is not None:
                    cmd = text.split()[0]
                    events.append(ParsedEvent(ts, repo, "command", {"cmd": cmd, "msg": text[:140]}))

            elif t == "assistant":
                msg = obj.get("message", {}) or {}
                model_seen = msg.get("model") or model_seen
                msg_id = msg.get("id")
                usage = msg.get("usage", {}) or {}
                # Claude Code splits one logical assistant turn (thinking / text /
                # each tool_use block) across multiple JSONL lines that all share
                # the same message.id and all repeat the SAME consolidated,
                # non-delta usage object. Only fold usage in once per unique
                # message.id -- otherwise tokens/cost get summed once per split
                # line (measured ~7x inflation vs. a deduped baseline on a real
                # transcript). Lines with no id (older format) always count,
                # since we cannot tell whether they duplicate a prior turn.
                is_new_turn = msg_id is None or msg_id != last_assistant_msg_id
                if msg_id is not None:
                    last_assistant_msg_id = msg_id
                if is_new_turn:
                    in_tok = int(usage.get("input_tokens", 0) or 0)
                    out_tok = int(usage.get("output_tokens", 0) or 0)
                    cache_write = int(usage.get("cache_creation_input_tokens", 0) or 0)
                    # Headline tokens = generation work (input + output + cache_creation).
                    # cache_read_input_tokens is intentionally excluded from both tokens
                    # and cost (not even bound to a variable): long-lived sessions can
                    # re-read the same 80k-token cached system prompt thousands of times --
                    # a single 8h session can easily accumulate 670M cache_read tokens
                    # against just 1.3M output, inflating BOTH figures by ~100x in a way
                    # that does not reflect actual generation effort. Excluding it from
                    # both keeps the dashboard story consistent: tokens × avg-rate ≈ cost.
                    turn_tokens = in_tok + out_tok + cache_write
                    tokens += turn_tokens
                    if ts is not None and turn_tokens > 0:
                        hour_key = ts.replace(minute=0, second=0, microsecond=0)
                        hourly_tokens[hour_key] = hourly_tokens.get(hour_key, 0) + turn_tokens
                    input_price, output_price = _price(model_seen)
                    cost += (in_tok / 1_000_000) * input_price
                    cost += (out_tok / 1_000_000) * output_price
                    # Cache write (one-time) is 25% more expensive than input.
                    cost += (cache_write / 1_000_000) * input_price * 1.25

                content = msg.get("content", [])
                if isinstance(content, list) and ts is not None:
                    for c in content:
                        if not isinstance(c, dict) or c.get("type") != "tool_use":
                            continue
                        tool = c.get("name", "")
                        ti = c.get("input", {}) or {}
                        if tool in _EDIT_TOOLS:
                            edits += 1
                        if tool in ("Task", "Agent"):
                            target = ti.get("subagent_type") or ti.get("description", "")
                            events.append(
                                ParsedEvent(
                                    ts,
                                    repo,
                                    "delegate",
                                    {
                                        "from": agent_name or "main",
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
                                ParsedEvent(ts, repo, "skill", {"skill": str(skill_name)})
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
                                    repo,
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
                            repo,
                            "permission",
                            {
                                "level": obj.get("level", "ask"),
                                "action": obj.get("action", ""),
                                "granted": bool(obj.get("granted", False)),
                            },
                        )
                    )

            # Unknown types are silently dropped.

    if session_id is None or started_at is None or last_ts is None:
        return None, []

    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0

    summary = SessionSummary(
        session_id=session_id,
        repo=repo,
        started_at=started_at,
        last_event_at=last_ts,
        agent=agent_name,
        task=task_text,
        status="completed",
        tokens=tokens,
        cost=round(cost, 4),
        edits=edits,
        file_path=str(path),
        file_mtime=mtime,
    )
    summary.hourly_tokens = hourly_tokens
    return summary, events


def iter_jsonl_files(projects_dir: Path) -> Iterator[Path]:
    if not projects_dir.is_dir():
        return iter(())
    return projects_dir.rglob("*.jsonl")
