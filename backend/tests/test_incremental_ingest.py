"""Incremental ingest: per-file byte-offset cursors (ingest_file_state) let
an ingest tick skip unchanged files without opening them, parse only the
bytes appended to a growing file, and fully reparse-and-replace a
shrunk/rotated file -- see app.services.ingest module docstring for the
decision tree. Mirrors tests/test_token_accounting.py's fixture patterns.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

import app.db as db_mod  # read db_mod._sessionmaker at call time; monkeypatches rebind it


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _user_line(session_id: str, cwd: str, ts: datetime, text: str = "go") -> str:
    return json.dumps({
        "type": "user",
        "sessionId": session_id,
        "cwd": cwd,
        "timestamp": _iso(ts),
        "message": {"content": text},
    })


def _assistant_line(
    session_id: str,
    cwd: str,
    ts: datetime,
    msg_id: str,
    in_tok: int,
    out_tok: int,
    content: list | None = None,
    model: str = "claude-sonnet-4-5",
) -> str:
    return json.dumps({
        "type": "assistant",
        "sessionId": session_id,
        "cwd": cwd,
        "timestamp": _iso(ts),
        "message": {
            "id": msg_id,
            "model": model,
            "content": content or [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
        },
    })


def _turn_cost(in_tok: int, out_tok: int) -> float:
    """Mirrors jsonl_parser._price()'s claude-sonnet-4-5 rate ($3/$15 per M
    input/output tokens)."""
    return (in_tok / 1_000_000) * 3.0 + (out_tok / 1_000_000) * 15.0


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Point CLAUDE_DIR/REPO_ROOTS/DB_PATH at tmp_path and reset cached
    settings + the DB engine so a fresh ingest_all() call picks them up.
    Returns (repo_dir, projects_dir).
    """
    repo = tmp_path / "myrepo"
    repo.mkdir()
    claude = tmp_path / "claude"
    proj = claude / "projects" / "myrepo-encoded"
    proj.mkdir(parents=True)

    monkeypatch.setenv("CLAUDE_DIR", str(claude))
    monkeypatch.setenv("REPO_ROOTS", str(repo))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite"))

    from app import config
    config.get_settings.cache_clear()
    db_mod._engine = None
    db_mod._sessionmaker = None
    return repo, proj


@pytest.mark.asyncio
async def test_append_only_growth_is_exact_across_ticks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Across 5 ingest ticks: a plain append, a message whose two split
    JSONL lines straddle the increment boundary (must count once, not
    twice), and a partial trailing line (no \\n) that only gets counted once
    it's completed on a later tick.
    """
    repo, proj = _setup_env(tmp_path, monkeypatch)
    from app.models.session_summary import SessionSummaryRow
    from app.services.ingest import ingest_all

    cwd = str(repo)
    now = datetime.now(tz=UTC).replace(microsecond=0)
    sid = "grow-session"
    path = proj / f"{sid}.jsonl"

    # Tick 1: one ordinary message.
    path.write_text(_user_line(sid, cwd, now) + "\n" + _assistant_line(sid, cwd, now, "m1", 10_000, 5_000) + "\n")
    r1 = await ingest_all()
    assert r1["new"] == 1

    async with db_mod._sessionmaker() as session:
        row = await session.get(SessionSummaryRow, sid)
    assert row.tokens == 15_000
    assert row.cost == pytest.approx(_turn_cost(10_000, 5_000), abs=1e-9)

    # Tick 2: append the FIRST of two split lines for message "m2" (a text
    # block) -- both split lines will share id "m2" and the SAME usage.
    m2_usage = (20_000, 8_000)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(_assistant_line(sid, cwd, now, "m2", *m2_usage, content=[{"type": "text", "text": "thinking"}]) + "\n")
    r2 = await ingest_all()
    assert r2["updated"] == 1

    async with db_mod._sessionmaker() as session:
        row = await session.get(SessionSummaryRow, sid)
    expected_after_m2 = 15_000 + sum(m2_usage)
    assert row.tokens == expected_after_m2
    assert row.cost == pytest.approx(
        _turn_cost(10_000, 5_000) + _turn_cost(*m2_usage), abs=1e-9
    )

    # Tick 3: append the SECOND split line for "m2" (a tool_use block, same
    # id, same usage) -- this is the boundary-straddling case: it must NOT
    # add m2's tokens/cost a second time.
    with path.open("a", encoding="utf-8") as fh:
        fh.write(
            _assistant_line(
                sid, cwd, now, "m2", *m2_usage,
                content=[{"type": "tool_use", "name": "Read", "input": {"file_path": "x.py"}}],
            ) + "\n"
        )
    r3 = await ingest_all()
    assert r3["updated"] == 1

    async with db_mod._sessionmaker() as session:
        row = await session.get(SessionSummaryRow, sid)
    assert row.tokens == expected_after_m2  # unchanged -- m2 not double-counted
    assert row.cost == pytest.approx(
        _turn_cost(10_000, 5_000) + _turn_cost(*m2_usage), abs=1e-9
    )
    assert row.edits == 0  # Read isn't an edit tool -- content WAS still processed

    # Tick 4: append message "m3" WITHOUT a trailing newline -- a
    # mid-write, not-yet-flushed line.
    m3_usage = (4_000, 1_000)
    partial = _assistant_line(sid, cwd, now, "m3", *m3_usage)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(partial)  # no trailing "\n"
    r4 = await ingest_all()

    async with db_mod._sessionmaker() as session:
        row = await session.get(SessionSummaryRow, sid)
    assert row.tokens == expected_after_m2  # m3 not counted yet
    # The file "changed" (size grew) but produced no complete new line, so
    # it's neither a fresh "new" row nor a numeric "updated" merge.
    assert r4["skipped"] >= 1

    # Tick 5: complete the line -- now it must be counted exactly once.
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n")
    r5 = await ingest_all()
    assert r5["updated"] == 1

    async with db_mod._sessionmaker() as session:
        row = await session.get(SessionSummaryRow, sid)
    expected_final = expected_after_m2 + sum(m3_usage)
    assert row.tokens == expected_final
    assert row.cost == pytest.approx(
        _turn_cost(10_000, 5_000) + _turn_cost(*m2_usage) + _turn_cost(*m3_usage), abs=1e-9
    )

    # Hourly buckets accumulated additively across every tick (single hour
    # bucket since all timestamps share the same `now`).
    from app.models.session_hour import SessionHourRow
    async with db_mod._sessionmaker() as session:
        hour_rows = (await session.execute(
            select(SessionHourRow).where(SessionHourRow.session_id == sid)
        )).scalars().all()
    assert sum(r.tokens for r in hour_rows) == expected_final

    # message_ledger has exactly the 3 distinct ids, each counted once.
    from app.models.message_ledger import MessageLedgerRow
    async with db_mod._sessionmaker() as session:
        ledger_rows = (await session.execute(select(MessageLedgerRow))).scalars().all()
    assert {r.message_id for r in ledger_rows} == {"m1", "m2", "m3"}


@pytest.mark.asyncio
async def test_shrink_replaces_prior_contribution_not_adds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file that shrinks (truncated + rewritten smaller) must be fully
    reparsed and its new totals must REPLACE the old ones -- including
    dropping the message_ledger rows for ids no longer present.
    """
    repo, proj = _setup_env(tmp_path, monkeypatch)
    from app.models.message_ledger import MessageLedgerRow
    from app.models.session_summary import SessionSummaryRow
    from app.services.ingest import ingest_all

    cwd = str(repo)
    now = datetime.now(tz=UTC).replace(microsecond=0)
    sid = "shrink-session"
    path = proj / f"{sid}.jsonl"

    path.write_text(
        _user_line(sid, cwd, now) + "\n"
        + _assistant_line(sid, cwd, now, "s-m1", 10_000, 5_000) + "\n"
        + _assistant_line(sid, cwd, now, "s-m2", 20_000, 8_000) + "\n"
    )
    await ingest_all()

    async with db_mod._sessionmaker() as session:
        row = await session.get(SessionSummaryRow, sid)
    assert row.tokens == 15_000 + 28_000

    # Shrink: rewrite in place with only the first message (e.g. the
    # transcript was truncated/rotated).
    path.write_text(_user_line(sid, cwd, now) + "\n" + _assistant_line(sid, cwd, now, "s-m1", 10_000, 5_000) + "\n")
    result = await ingest_all()
    assert result["updated"] >= 1

    async with db_mod._sessionmaker() as session:
        row = await session.get(SessionSummaryRow, sid)
        ledger_ids = {
            r.message_id
            for r in (await session.execute(select(MessageLedgerRow))).scalars().all()
        }
    assert row.tokens == 15_000  # REPLACED, not 15_000 + 43_000
    assert row.cost == pytest.approx(_turn_cost(10_000, 5_000), abs=1e-9)
    assert ledger_ids == {"s-m1"}  # s-m2's ledger row was dropped, not left dangling


@pytest.mark.asyncio
async def test_replace_via_inode_change_replaces_not_adds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file replaced by delete+recreate at the same path (new inode, same
    or larger size -- so the shrink-by-size check alone wouldn't catch it)
    must still be detected as a replace, not treated as ordinary growth.
    """
    repo, proj = _setup_env(tmp_path, monkeypatch)
    from app.models.session_summary import SessionSummaryRow
    from app.services.ingest import ingest_all

    cwd = str(repo)
    now = datetime.now(tz=UTC).replace(microsecond=0)
    sid = "replace-session"
    path = proj / f"{sid}.jsonl"

    path.write_text(
        _user_line(sid, cwd, now) + "\n"
        + _assistant_line(sid, cwd, now, "r-m1", 10_000, 5_000) + "\n"
        + _assistant_line(sid, cwd, now, "r-m2", 20_000, 8_000) + "\n"
    )
    await ingest_all()

    async with db_mod._sessionmaker() as session:
        row = await session.get(SessionSummaryRow, sid)
    assert row.tokens == 15_000 + 28_000

    path.unlink()  # guarantees a fresh inode on recreation
    path.write_text(
        _user_line(sid, cwd, now) + "\n"
        + _assistant_line(sid, cwd, now, "r-m3", 1_000, 500, content=[{"type": "text", "text": "brand new content padding"}]) + "\n"
    )
    result = await ingest_all()
    assert result["updated"] >= 1

    async with db_mod._sessionmaker() as session:
        row = await session.get(SessionSummaryRow, sid)
    assert row.tokens == 1_500  # REPLACED with the new file's own total


@pytest.mark.asyncio
async def test_unchanged_file_is_skipped_without_reparsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Goal 1: the skip decision happens BEFORE any open()/parse call -- an
    unchanged file must not trigger a re-parse at all.
    """
    repo, proj = _setup_env(tmp_path, monkeypatch)
    from app.models.session_summary import SessionSummaryRow
    from app.services.ingest import ingest_all

    cwd = str(repo)
    now = datetime.now(tz=UTC).replace(microsecond=0)
    sid = "stable-session"
    path = proj / f"{sid}.jsonl"
    path.write_text(_user_line(sid, cwd, now) + "\n" + _assistant_line(sid, cwd, now, "u-m1", 1_000, 500) + "\n")

    first = await ingest_all()
    assert first["new"] == 1

    import app.services.ingest as ingest_mod

    def _boom(*args, **kwargs):
        raise AssertionError("parse_jsonl_incremental must not be called for an unchanged file")

    monkeypatch.setattr(ingest_mod, "parse_jsonl_incremental", _boom)

    second = await ingest_all()
    assert second["new"] == 0
    assert second["updated"] == 0
    assert second["skipped"] >= 1

    async with db_mod._sessionmaker() as session:
        row = await session.get(SessionSummaryRow, sid)
    assert row.tokens == 1_500


@pytest.mark.asyncio
async def test_health_responds_promptly_during_slow_synchronous_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Goal 2: a REAL, synchronous, blocking parse call running inside the
    background ingest task must not stall /api/health -- proves
    parse_jsonl_incremental is actually offloaded via asyncio.to_thread,
    not just that the mocked-out bootstrap in test_health.py awaits nicely.
    """
    repo, proj = _setup_env(tmp_path, monkeypatch)
    cwd = str(repo)
    now = datetime.now(tz=UTC).replace(microsecond=0)
    (proj / "slow.jsonl").write_text(
        _user_line("slow-session", cwd, now) + "\n"
        + _assistant_line("slow-session", cwd, now, "sp-m1", 1_000, 500) + "\n"
    )

    import app.services.ingest as ingest_mod
    real_fn = ingest_mod.parse_jsonl_incremental

    def _slow(*args, **kwargs):
        time.sleep(1.5)  # blocking sync sleep -- would stall the loop if not off-threaded
        return real_fn(*args, **kwargs)

    monkeypatch.setattr(ingest_mod, "parse_jsonl_incremental", _slow)

    from app.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        # Give the background bootstrap ingest task a moment to actually
        # enter the slow parse call before measuring /api/health against it.
        await asyncio.sleep(0.2)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = time.monotonic()
            res = await asyncio.wait_for(client.get("/api/health"), timeout=1.0)
            elapsed = time.monotonic() - started

    assert res.status_code == 200
    assert res.json() == {"ok": True}
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_watcher_signal_ingests_without_waiting_for_sweep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Goal 4: a path pushed onto the ingest signal queue must trigger an
    event-driven ingest_all(changed_paths=...) call quickly -- nowhere near
    the (here, deliberately huge) safety-sweep interval.
    """
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "INGEST_SWEEP_SEC", 100)
    monkeypatch.setattr(main_mod, "INGEST_DEBOUNCE_SEC", 0.05)

    calls: list[dict] = []

    async def _fake_ingest_all(*args, **kwargs):
        calls.append(kwargs)
        return {"new": 0, "updated": 0, "skipped": 0, "events": 0, "elapsed_s": 0}

    monkeypatch.setattr("app.services.ingest.ingest_all", _fake_ingest_all)

    queue: asyncio.Queue[Path] = asyncio.Queue()
    task = asyncio.create_task(main_mod._ingest_loop(queue))
    try:
        # Let the bootstrap call land and the loop settle into its wait.
        for _ in range(50):
            if calls:
                break
            await asyncio.sleep(0.02)
        assert calls, "bootstrap ingest was not invoked"

        target = tmp_path / "changed.jsonl"
        queue.put_nowait(target)

        for _ in range(150):
            if len(calls) >= 2:
                break
            await asyncio.sleep(0.02)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert len(calls) >= 2, "event-driven tick never fired"
    event_call = calls[-1]
    assert event_call.get("changed_paths") == {target}


@pytest.mark.asyncio
async def test_version_bump_rebuild_records_offsets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A version-triggered rebuild must establish an ingest_file_state
    cursor for every JSONL-derived row it (re)creates, so the NEXT tick can
    go straight to the fast unchanged-skip path instead of re-walking with
    no cursors at all.
    """
    repo, proj = _setup_env(tmp_path, monkeypatch)
    from app.db import init_db
    from app.models.ingest_file_state import IngestFileStateRow
    from app.models.ingest_meta import SINGLETON_ID, IngestMetaRow
    from app.models.session_summary import SessionSummaryRow

    cwd = str(repo)
    now = datetime.now(tz=UTC).replace(microsecond=0)
    sid = "healed-session"
    path = proj / f"{sid}.jsonl"
    path.write_text(_user_line(sid, cwd, now) + "\n" + _assistant_line(sid, cwd, now, "v-m1", 2_000, 1_000) + "\n")

    await init_db()
    async with db_mod._sessionmaker() as session:
        session.add(IngestMetaRow(id=SINGLETON_ID, version=1))  # behind INGEST_VERSION
        await session.commit()

    from app.services.ingest import INGEST_VERSION, ingest_all

    result = await ingest_all()
    assert result["new"] == 1

    async with db_mod._sessionmaker() as session:
        meta = await session.get(IngestMetaRow, SINGLETON_ID)
        state = await session.get(IngestFileStateRow, str(path))
        row = await session.get(SessionSummaryRow, sid)

    assert meta is not None
    assert meta.version == INGEST_VERSION
    assert state is not None
    assert state.byte_offset == path.stat().st_size
    assert state.session_id == sid
    assert row.tokens == 3_000

    # Confirms the cursor actually short-circuits the next tick: monkeypatch
    # the parser to fail and prove it's never invoked for this now-unchanged
    # file.
    import app.services.ingest as ingest_mod

    def _boom(*args, **kwargs):
        raise AssertionError("must not reparse an unchanged, already-healed file")

    monkeypatch.setattr(ingest_mod, "parse_jsonl_incremental", _boom)
    second = await ingest_all()
    assert second["new"] == 0
    assert second["updated"] == 0


@pytest.mark.asyncio
async def test_shrink_across_hours_drops_stale_hour_bucket_for_session_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session file whose messages span two different UTC hours, then
    shrunk (same path, full reparse) to only the first hour, must drop the
    SECOND hour's SessionHourRow bucket entirely -- not just stop adding to
    it -- so the heatmap/48h charts don't keep serving stale tokens for an
    hour the file no longer covers.
    """
    repo, proj = _setup_env(tmp_path, monkeypatch)
    from app.models.session_hour import SessionHourRow
    from app.models.session_summary import SessionSummaryRow
    from app.services.ingest import ingest_all

    cwd = str(repo)
    now = datetime.now(tz=UTC).replace(minute=30, second=0, microsecond=0)
    hour1 = now - timedelta(hours=3)
    hour2 = now - timedelta(hours=2)
    sid = "two-hour-session"
    path = proj / f"{sid}.jsonl"

    path.write_text(
        _user_line(sid, cwd, hour1) + "\n"
        + _assistant_line(sid, cwd, hour1, "h1-m1", 10_000, 5_000) + "\n"
        + _assistant_line(sid, cwd, hour2, "h2-m1", 20_000, 8_000) + "\n"
    )
    await ingest_all()

    async with db_mod._sessionmaker() as session:
        row = await session.get(SessionSummaryRow, sid)
        hour_rows = (await session.execute(
            select(SessionHourRow).where(SessionHourRow.session_id == sid)
        )).scalars().all()
    assert row.tokens == 15_000 + 28_000
    assert len(hour_rows) == 2
    assert sum(r.tokens for r in hour_rows) == 43_000

    # Shrink to ONLY the first hour's message -- same path, so this is the
    # genuine same-file full-reparse case.
    path.write_text(
        _user_line(sid, cwd, hour1) + "\n"
        + _assistant_line(sid, cwd, hour1, "h1-m1", 10_000, 5_000) + "\n"
    )
    result = await ingest_all()
    assert result["updated"] >= 1

    async with db_mod._sessionmaker() as session:
        row = await session.get(SessionSummaryRow, sid)
        hour_rows = (await session.execute(
            select(SessionHourRow).where(SessionHourRow.session_id == sid)
        )).scalars().all()
    assert row.tokens == 15_000
    assert len(hour_rows) == 1  # hour2's bucket is GONE, not left stale
    assert hour_rows[0].tokens == 15_000

    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        heat = (await client.get("/api/stats/heatmap")).json()

    token_total = sum(sum(day) for day in heat["tokenGrid"])
    assert token_total == 15_000
    repo_tokens_total = sum(sum(v) for v in heat["repoTokens48h"].values())
    assert repo_tokens_total == 15_000


@pytest.mark.asyncio
async def test_shrink_across_hours_drops_stale_hour_bucket_for_subagent_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same as the session-file case above, but for a subagent file. Its
    SessionHourRow rows are keyed under ingest._subagent_hour_key(path) --
    a key exclusively owned by that one file -- so a shrink must drop ALL of
    its stale hours too, and the plain session-count grid must stay
    unaffected (a subagent call is not a session of its own).
    """
    repo, proj = _setup_env(tmp_path, monkeypatch)
    from app.models.session_hour import SessionHourRow
    from app.models.subagent_call import SubagentCallRow
    from app.services.ingest import _subagent_hour_key, ingest_all

    cwd = str(repo)
    now = datetime.now(tz=UTC).replace(minute=30, second=0, microsecond=0)
    hour1 = now - timedelta(hours=3)
    hour2 = now - timedelta(hours=2)
    parent_sid = "two-hour-parent"
    sub_dir = proj / parent_sid / "subagents"
    sub_dir.mkdir(parents=True)
    path = sub_dir / "agent-atwohour1.jsonl"

    path.write_text(
        _user_line(parent_sid, cwd, hour1) + "\n"
        + _assistant_line(parent_sid, cwd, hour1, "sub-h1-m1", 10_000, 5_000) + "\n"
        + _assistant_line(parent_sid, cwd, hour2, "sub-h2-m1", 20_000, 8_000) + "\n"
    )
    result1 = await ingest_all()
    assert result1["new"] == 1

    hour_key = _subagent_hour_key(path)
    async with db_mod._sessionmaker() as session:
        sc = (await session.execute(
            select(SubagentCallRow).where(SubagentCallRow.file_path == str(path))
        )).scalar_one()
        hour_rows = (await session.execute(
            select(SessionHourRow).where(SessionHourRow.session_id == hour_key)
        )).scalars().all()
    assert sc.tokens == 15_000 + 28_000
    assert len(hour_rows) == 2
    assert sum(r.tokens for r in hour_rows) == 43_000

    # Shrink to ONLY the first hour's message -- same path.
    path.write_text(
        _user_line(parent_sid, cwd, hour1) + "\n"
        + _assistant_line(parent_sid, cwd, hour1, "sub-h1-m1", 10_000, 5_000) + "\n"
    )
    result2 = await ingest_all()
    assert result2["updated"] >= 1

    async with db_mod._sessionmaker() as session:
        sc = (await session.execute(
            select(SubagentCallRow).where(SubagentCallRow.file_path == str(path))
        )).scalar_one()
        hour_rows = (await session.execute(
            select(SessionHourRow).where(SessionHourRow.session_id == hour_key)
        )).scalars().all()
    assert sc.tokens == 15_000
    assert len(hour_rows) == 1  # hour2's bucket is GONE
    assert hour_rows[0].tokens == 15_000

    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        heat = (await client.get("/api/stats/heatmap")).json()

    token_total = sum(sum(day) for day in heat["tokenGrid"])
    assert token_total == 15_000
    # A subagent call isn't "a session" -- the plain session-count grid must
    # stay empty even though its tokens show up in tokenGrid.
    assert sum(sum(day) for day in heat["grid"]) == 0


@pytest.mark.asyncio
async def test_file_growing_during_parse_offset_matches_bytes_actually_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A writer can append more bytes to a file AFTER the pre-scan stat()
    (app.services.ingest._scan_candidates) but WHILE parse_jsonl_incremental
    is doing its own (later, independent) stat()+read() inside the
    to_thread call. The persisted byte_offset must reflect exactly what was
    actually parsed -- up to the last complete newline in whatever
    parse_jsonl_incremental itself read -- never the earlier, now-stale
    pre-scan size. The next tick must then pick up the remainder with no
    double count.
    """
    repo, proj = _setup_env(tmp_path, monkeypatch)
    from app.models.ingest_file_state import IngestFileStateRow
    from app.models.session_summary import SessionSummaryRow
    from app.services.ingest import ingest_all

    cwd = str(repo)
    now = datetime.now(tz=UTC).replace(microsecond=0)
    sid = "grow-during-parse-session"
    path = proj / f"{sid}.jsonl"

    m1_usage = (10_000, 5_000)
    m2_usage = (20_000, 8_000)
    m3_usage = (4_000, 1_000)

    # Tick 1: establish a cursor covering just m1.
    path.write_text(_user_line(sid, cwd, now) + "\n" + _assistant_line(sid, cwd, now, "m1", *m1_usage) + "\n")
    r1 = await ingest_all()
    assert r1["new"] == 1

    # Append m2 (COMPLETE line) -- this is what the pre-scan stat() for tick
    # 2 will see, and is the amount that should legitimately get parsed.
    with path.open("a", encoding="utf-8") as fh:
        fh.write(_assistant_line(sid, cwd, now, "m2", *m2_usage) + "\n")
    size_after_m2 = path.stat().st_size

    # A concurrent writer appends a PARTIAL line for m3 (no trailing
    # newline) -- but only once this thread's own parse_jsonl_incremental
    # call has actually started, i.e. strictly AFTER _scan_candidates's
    # pre-scan stat() already ran for this tick.
    partial_m3 = _assistant_line(sid, cwd, now, "m3", *m3_usage)
    grew = {"done": False}

    import app.services.ingest as ingest_mod
    real_parse = ingest_mod.parse_jsonl_incremental

    def _grow_then_parse(path_arg, repo_paths, start_offset, seen_ids, **kwargs):
        if not grew["done"]:
            grew["done"] = True
            with path_arg.open("a", encoding="utf-8") as fh:
                fh.write(partial_m3)  # no trailing "\n" -- writer mid-flush
        return real_parse(path_arg, repo_paths, start_offset, seen_ids, **kwargs)

    monkeypatch.setattr(ingest_mod, "parse_jsonl_incremental", _grow_then_parse)

    r2 = await ingest_all()
    assert r2["updated"] == 1
    assert grew["done"], "the growth-during-parse hook never fired"

    async with db_mod._sessionmaker() as session:
        row = await session.get(SessionSummaryRow, sid)
        state = await session.get(IngestFileStateRow, str(path))

    expected_after_m2 = sum(m1_usage) + sum(m2_usage)
    assert row.tokens == expected_after_m2  # m3's partial line was NOT counted
    # The cursor must land exactly at the bytes actually parsed (through the
    # end of m2's line) -- neither the stale pre-scan size nor a cursor that
    # swallowed m3's still-incomplete bytes.
    assert state.byte_offset == size_after_m2

    # Tick 3: complete m3's line -- the remainder must be picked up exactly
    # once, with no double count of m2.
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n")
    r3 = await ingest_all()
    assert r3["updated"] == 1

    async with db_mod._sessionmaker() as session:
        row = await session.get(SessionSummaryRow, sid)
    expected_final = expected_after_m2 + sum(m3_usage)
    assert row.tokens == expected_final
