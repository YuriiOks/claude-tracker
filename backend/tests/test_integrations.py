"""Integration adapters degrade gracefully without credentials."""
from __future__ import annotations

import pytest


def test_linear_returns_none_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    import asyncio

    from app.services.integrations import linear_ticket_for_branch

    assert asyncio.run(linear_ticket_for_branch("feat/ACM-026-x")) is None


def test_linear_returns_none_when_branch_has_no_ticket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "fake")
    import asyncio

    from app.services.integrations import linear_ticket_for_branch

    assert asyncio.run(linear_ticket_for_branch("main")) is None


def test_langfuse_returns_none_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    import asyncio

    from app.services.integrations import langfuse_cost_for_session

    assert asyncio.run(langfuse_cost_for_session("abc")) is None


def test_github_returns_none_when_gh_missing_or_main(tmp_path) -> None:
    from app.services.integrations import github_pr_for_branch

    assert github_pr_for_branch(tmp_path, "") is None
    assert github_pr_for_branch(tmp_path, "main") is None
