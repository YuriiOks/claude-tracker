"""Snapshot test: Pydantic Repo dump matches the data.js camelCase shape."""
from __future__ import annotations

from app.schemas.repo import Permissions, Repo, RepoStats


def test_repo_camel_case_round_trip() -> None:
    r = Repo(
        id="jupus",
        name="jupus",
        org="jupus-legal",
        path="~/Desktop/jupus",
        description="Legal tech",
        branch="main",
        language="Python",
        accent="#d97757",
        is_active=True,
        stats=RepoStats(
            sessions_today=14,
            sessions_week=73,
            tokens_week=4_820_000,
            cost_week=38.42,
            files_edited=47,
            avg_session="8m 42s",
        ),
        agents=["jupus-orchestrator"],
        permissions=Permissions(allow=142, deny=4, ask=8),
    )
    dumped = r.model_dump(by_alias=True)
    assert dumped["id"] == "jupus"
    assert dumped["isActive"] is True
    assert dumped["stats"]["tokensWeek"] == 4_820_000
    assert dumped["stats"]["costWeek"] == 38.42
    assert dumped["stats"]["avgSession"] == "8m 42s"
    assert dumped["stats"]["filesEdited"] == 47
    assert dumped["permissions"] == {"allow": 142, "deny": 4, "ask": 8}
    assert dumped["skills"] == []


def test_event_alias_from() -> None:
    from app.schemas.event import LiveEvent

    e = LiveEvent.model_validate(
        {"t": -10, "repo": "jupus", "kind": "delegate", "from": "a", "to": "b"}
    )
    dumped = e.model_dump(by_alias=True, exclude_none=True)
    assert dumped["from"] == "a"
    assert dumped["to"] == "b"
    assert "from_" not in dumped
