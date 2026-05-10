"""Pytest fixtures — shared across the test suite."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CLAUDE_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("REPO_ROOTS", "")
    # Reset settings cache.
    from app import config

    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()
