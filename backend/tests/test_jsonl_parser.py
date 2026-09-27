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
