from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def _write_jsonl(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(l) for l in lines) + "\n")


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
