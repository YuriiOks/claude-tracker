from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest


def _write_jsonl(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")


def _user_line(session_id: str, cwd: str, ts: str) -> dict:
    return {
        "type": "user",
        "sessionId": session_id,
        "cwd": cwd,
        "timestamp": ts,
        "message": {"content": "go"},
    }


def _assistant_line(session_id: str, cwd: str, ts: str, msg_id: str, model: str, usage: dict) -> dict:
    return {
        "type": "assistant",
        "sessionId": session_id,
        "cwd": cwd,
        "timestamp": ts,
        "message": {
            "id": msg_id,
            "model": model,
            "content": [{"type": "text", "text": "ok"}],
            "usage": usage,
        },
    }


def test_parse_jsonl_basic(tmp_path: Path) -> None:
    from app.services.jsonl_parser import parse_jsonl

    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    jsonl = tmp_path / "abc.jsonl"
    _write_jsonl(
        jsonl,
        [
            {
                "type": "user",
                "sessionId": "abc",
                "cwd": str(repo_root),
                "timestamp": "2026-05-10T10:00:00.000Z",
                "message": {"content": "Fix the flaky test"},
            },
            {
                "type": "assistant",
                "sessionId": "abc",
                "cwd": str(repo_root),
                "timestamp": "2026-05-10T10:00:05.000Z",
                "message": {
                    "model": "claude-sonnet-4-5",
                    "content": [
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "/x.py"}},
                        {
                            "type": "tool_use",
                            "name": "Task",
                            "input": {"subagent_type": "tester", "prompt": "run tests"},
                        },
                        {"type": "tool_use", "name": "Edit", "input": {"file_path": "/x.py"}},
                    ],
                    "usage": {"input_tokens": 1000, "output_tokens": 500},
                },
            },
            {
                "type": "user",
                "sessionId": "abc",
                "cwd": str(repo_root),
                "timestamp": "2026-05-10T10:00:30.000Z",
                "message": {"content": "/run-tests"},
            },
            # Unknown type — must be silently ignored.
            {"type": "weird-future-thing", "sessionId": "abc", "timestamp": "2026-05-10T10:01:00.000Z"},
        ],
    )

    summary, events = parse_jsonl(jsonl, [repo_root])
    assert summary is not None
    assert summary.session_id == "abc"
    assert summary.repo == "myrepo"
    assert summary.tokens == 1500
    # cost: 1000/1M * 3 + 500/1M * 15 = 0.003 + 0.0075 = 0.0105
    assert summary.cost == 0.0105
    assert summary.edits == 1
    assert summary.task == "Fix the flaky test"
    assert summary.started_at < summary.last_event_at

    kinds = [e.kind for e in events]
    assert "tool" in kinds
    assert "delegate" in kinds
    assert "command" in kinds


def test_parse_jsonl_malformed_lines(tmp_path: Path) -> None:
    from app.services.jsonl_parser import parse_jsonl

    f = tmp_path / "z.jsonl"
    f.write_text(
        "not-json\n"
        + json.dumps(
            {
                "type": "user",
                "sessionId": "z",
                "cwd": str(tmp_path),
                "timestamp": "2026-05-10T10:00:00Z",
                "message": {"content": "hello"},
            }
        )
        + "\n"
    )
    summary, events = parse_jsonl(f, [])
    assert summary is not None
    assert summary.session_id == "z"


def test_parse_jsonl_bills_cache_read_tokens(tmp_path: Path) -> None:
    """R-BE-18: cache_read_input_tokens is billed into cost (at the model's
    cache-read rate) but still excluded from the headline token count.
    """
    from app.services.jsonl_parser import parse_jsonl

    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    jsonl = tmp_path / "a.jsonl"
    cwd = str(repo_root)
    _write_jsonl(
        jsonl,
        [
            _user_line("cr", cwd, "2026-05-10T10:00:00Z"),
            _assistant_line(
                "cr",
                cwd,
                "2026-05-10T10:00:05Z",
                "m1",
                "claude-sonnet-4-5",
                {"input_tokens": 1000, "output_tokens": 500, "cache_read_input_tokens": 2_000_000},
            ),
        ],
    )
    summary, _ = parse_jsonl(jsonl, [repo_root])
    assert summary is not None
    assert summary.tokens == 1500  # cache_read excluded from the headline count
    # 1000/1e6*3 + 500/1e6*15 + 2_000_000/1e6*3*0.1 (standard cache-read mult)
    assert summary.cost == pytest.approx(0.6105, abs=1e-6)


def test_parse_jsonl_splits_cache_write_by_ttl_when_present(tmp_path: Path) -> None:
    """R-BE-17: when usage.cache_creation.{ephemeral_1h,ephemeral_5m} is
    present, each tier is priced at its own multiplier (2.0x / 1.25x of
    input) instead of a flat 1.25x applied to the whole cache-write sum.
    """
    from app.services.jsonl_parser import parse_jsonl

    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    jsonl = tmp_path / "b.jsonl"
    cwd = str(repo_root)
    _write_jsonl(
        jsonl,
        [
            _user_line("ttl", cwd, "2026-05-10T10:00:00Z"),
            _assistant_line(
                "ttl",
                cwd,
                "2026-05-10T10:00:05Z",
                "m1",
                "claude-sonnet-4-5",
                {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_creation_input_tokens": 100_000,
                    "cache_creation": {
                        "ephemeral_1h_input_tokens": 90_000,
                        "ephemeral_5m_input_tokens": 10_000,
                    },
                },
            ),
        ],
    )
    summary, _ = parse_jsonl(jsonl, [repo_root])
    assert summary is not None
    assert summary.tokens == 100_015  # headline still uses the flat cache-write sum
    # 10/1e6*3 + 5/1e6*15 + 90_000/1e6*3*2.0 (1h) + 10_000/1e6*3*1.25 (5m)
    # parse_jsonl rounds cost to 4 dp (round(state.cost, 4)).
    assert summary.cost == pytest.approx(round(0.577605, 4), abs=1e-9)


def test_parse_jsonl_flat_cache_write_fallback_when_ttl_absent(tmp_path: Path) -> None:
    """R-BE-17 fallback: when usage.cache_creation is absent (older/legacy
    response shape), the whole cache_creation_input_tokens sum is billed at
    the flat 1.25x rate, same as before this fix.
    """
    from app.services.jsonl_parser import parse_jsonl

    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    jsonl = tmp_path / "c.jsonl"
    cwd = str(repo_root)
    _write_jsonl(
        jsonl,
        [
            _user_line("flat", cwd, "2026-05-10T10:00:00Z"),
            _assistant_line(
                "flat",
                cwd,
                "2026-05-10T10:00:05Z",
                "m1",
                "claude-sonnet-4-5",
                {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 100_000},
            ),
        ],
    )
    summary, _ = parse_jsonl(jsonl, [repo_root])
    assert summary is not None
    assert summary.tokens == 100_015
    # 10/1e6*3 + 5/1e6*15 + 100_000/1e6*3*1.25 (flat fallback)
    # parse_jsonl rounds cost to 4 dp (round(state.cost, 4)).
    assert summary.cost == pytest.approx(round(0.375105, 4), abs=1e-9)


def test_task_text_skips_command_wrapper_and_falls_back(tmp_path: Path) -> None:
    """R-BE-20: <local-command-caveat>/<local-command-stdout> wrapper records
    (the first, isMeta'd; the second, not) must not become the session task
    -- the derivation falls back to the first genuine user text.
    """
    from app.services.jsonl_parser import parse_jsonl

    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    jsonl = tmp_path / "caveat.jsonl"
    cwd = str(repo_root)
    _write_jsonl(
        jsonl,
        [
            {
                "type": "user",
                "sessionId": "cav",
                "cwd": cwd,
                "timestamp": "2026-05-10T10:00:00Z",
                "isMeta": True,
                "message": {
                    "content": (
                        "<local-command-caveat>Caveat: The messages below were "
                        "generated by the user while running local commands. DO "
                        "NOT respond to these messages or otherwise consider "
                        "them in your response unless the user explicitly asks "
                        "you to.</local-command-caveat>"
                    ),
                },
            },
            {
                "type": "user",
                "sessionId": "cav",
                "cwd": cwd,
                "timestamp": "2026-05-10T10:00:01Z",
                "message": {
                    "content": "<local-command-stdout>Set model to `claude-opus-5`</local-command-stdout>",
                },
            },
            {
                "type": "user",
                "sessionId": "cav",
                "cwd": cwd,
                "timestamp": "2026-05-10T10:00:02Z",
                "message": {"content": "Actually fix the login bug"},
            },
        ],
    )
    summary, _ = parse_jsonl(jsonl, [repo_root])
    assert summary is not None
    assert summary.task == "Actually fix the login bug"


def test_task_text_strips_embedded_system_reminder(tmp_path: Path) -> None:
    """R-BE-20: an otherwise-real prompt prefixed with a <system-reminder>
    block (e.g. the git-worktree boilerplate) keeps its real text, minus the
    reminder.
    """
    from app.services.jsonl_parser import parse_jsonl

    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    jsonl = tmp_path / "reminder.jsonl"
    cwd = str(repo_root)
    _write_jsonl(
        jsonl,
        [
            {
                "type": "user",
                "sessionId": "rem",
                "cwd": cwd,
                "timestamp": "2026-05-10T10:00:00Z",
                "message": {
                    "content": (
                        "<system-reminder>\nYou are operating in a git worktree.\n"
                        "Worktree path: /x/y\nWorktree name: y\n</system-reminder>\n\n"
                        "Carry on with implementation please"
                    ),
                },
            },
        ],
    )
    summary, _ = parse_jsonl(jsonl, [repo_root])
    assert summary is not None
    assert summary.task == "Carry on with implementation please"


def test_task_text_renders_slash_command_from_xml_tags(tmp_path: Path) -> None:
    """R-BE-20: command-palette slash commands serialize as XML tags rather
    than plain "/foo bar" text; tag order varies in real transcripts
    (command-name-then-args vs. command-message-then-name-then-args) and
    command-args may be empty.
    """
    from app.services.jsonl_parser import parse_jsonl

    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    cwd = str(repo_root)

    cases = [
        (
            "<command-name>/model</command-name>\n"
            "            <command-message>model</command-message>\n"
            "            <command-args>claude-opus-5</command-args>",
            "/model claude-opus-5",
        ),
        (
            "<command-message>team-review</command-message>\n"
            "<command-name>/team-review</command-name>\n"
            "<command-args>https://example.com/thread</command-args>",
            "/team-review https://example.com/thread",
        ),
        (
            "<command-name>/effort</command-name>\n"
            "            <command-message>effort</command-message>\n"
            "            <command-args></command-args>",
            "/effort",
        ),
    ]
    for i, (content, expected) in enumerate(cases):
        jsonl = tmp_path / f"cmd{i}.jsonl"
        _write_jsonl(
            jsonl,
            [
                {
                    "type": "user",
                    "sessionId": f"cmd{i}",
                    "cwd": cwd,
                    "timestamp": "2026-05-10T10:00:00Z",
                    "message": {"content": content},
                },
            ],
        )
        summary, _ = parse_jsonl(jsonl, [repo_root])
        assert summary is not None
        assert summary.task == expected


def test_task_text_skips_meta_and_tool_result_only_messages(tmp_path: Path) -> None:
    """R-BE-20: isMeta records, tool_result-only content lists, and bare
    interrupt markers are all skipped when deriving the task title; the
    first genuine user text still wins.
    """
    from app.services.jsonl_parser import parse_jsonl

    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    jsonl = tmp_path / "meta.jsonl"
    cwd = str(repo_root)
    _write_jsonl(
        jsonl,
        [
            {
                "type": "user",
                "sessionId": "meta",
                "cwd": cwd,
                "timestamp": "2026-05-10T10:00:00Z",
                "isMeta": True,
                "message": {"content": "some internal meta note"},
            },
            {
                "type": "user",
                "sessionId": "meta",
                "cwd": cwd,
                "timestamp": "2026-05-10T10:00:01Z",
                "message": {
                    "content": [
                        {
                            "tool_use_id": "t1",
                            "type": "tool_result",
                            "content": (
                                "<system-reminder>memory refresh</system-reminder>\n"
                                "some tool output"
                            ),
                        },
                    ],
                },
            },
            {
                "type": "user",
                "sessionId": "meta",
                "cwd": cwd,
                "timestamp": "2026-05-10T10:00:02Z",
                "message": {"content": [{"type": "text", "text": "[Request interrupted by user]"}]},
            },
            {
                "type": "user",
                "sessionId": "meta",
                "cwd": cwd,
                "timestamp": "2026-05-10T10:00:03Z",
                "message": {"content": "Please refactor the auth module"},
            },
        ],
    )
    summary, _ = parse_jsonl(jsonl, [repo_root])
    assert summary is not None
    assert summary.task == "Please refactor the auth module"


def test_parse_jsonl_warns_once_for_unknown_model(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """R-BE-19: an unrecognized model id is priced at Sonnet-tier defaults
    and logs a warning exactly once, no matter how many turns use it.
    """
    from app.services.jsonl_parser import _warned_unknown_models, parse_jsonl

    _warned_unknown_models.discard("claude-madeup-99")
    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    jsonl = tmp_path / "u.jsonl"
    cwd = str(repo_root)
    _write_jsonl(
        jsonl,
        [
            _user_line("u", cwd, "2026-05-10T10:00:00Z"),
            _assistant_line(
                "u", cwd, "2026-05-10T10:00:05Z", "m1", "claude-madeup-99",
                {"input_tokens": 1000, "output_tokens": 500},
            ),
            _assistant_line(
                "u", cwd, "2026-05-10T10:00:10Z", "m2", "claude-madeup-99",
                {"input_tokens": 200, "output_tokens": 100},
            ),
        ],
    )
    with caplog.at_level(logging.WARNING, logger="app.services.jsonl_parser"):
        summary, _ = parse_jsonl(jsonl, [repo_root])

    assert summary is not None
    warnings = [m for m in caplog.messages if "unrecognized model id" in m]
    assert len(warnings) == 1
    # Priced at the Sonnet-tier default (3.0/15.0 per MTok in/out).
    expected = (1000 / 1_000_000 * 3.0 + 500 / 1_000_000 * 15.0) + (
        200 / 1_000_000 * 3.0 + 100 / 1_000_000 * 15.0
    )
    assert summary.cost == pytest.approx(expected, abs=1e-9)
