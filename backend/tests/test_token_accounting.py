"""End-to-end token/cost accounting: a session's real usage is main +
continuation + direct-subagent + workflow-agent, each assistant message
counted exactly once, and every total (/stats/dashboard, repo_stats,
/api/cost, heatmap hourly buckets, /api/sessions) must include all of it.

Fixture tree lives at tests/fixtures/token_accounting/project/ and mirrors
the real ~/.claude/projects/<project>/ layout:
  11111111....jsonl                                        main session
  22222222....jsonl                                        continuation
                                                             (shares one
                                                             message id with
                                                             main -- must be
                                                             counted once)
  11111111..../subagents/agent-adirect001.jsonl             direct Task()
  11111111..../subagents/workflows/wf_test001/
    agent-aworkflow01.jsonl                                 workflow agent

Known usage (see the fixture .jsonl files):
  main:      shared-msg-001 (100k in / 50k out = 150k tok) + main-msg-002
             (200k in / 100k out = 300k tok)         -> 450_000 tok, $3.15
  cont:      shared-msg-001 (duplicate, owned by main) + cont-msg-003
             (50k in / 25k out = 75k tok)             -> 75_000 tok (after
             dedup), $0.525
  direct:    direct-msg-004 (40k in / 10k out)        -> 50_000 tok, $0.27
  workflow:  workflow-msg-005 (80k in / 20k out)      -> 100_000 tok, $0.54
All turns use claude-sonnet-4-5 pricing ($3/$15 per M input/output tokens).
"""
from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "token_accounting" / "project"

MAIN_TOKENS = 450_000
MAIN_COST = 3.15
CONT_TOKENS = 75_000
CONT_COST = 0.525
DIRECT_TOKENS = 50_000
DIRECT_COST = 0.27
WORKFLOW_TOKENS = 100_000
WORKFLOW_COST = 0.54
TOTAL_TOKENS = MAIN_TOKENS + CONT_TOKENS + DIRECT_TOKENS + WORKFLOW_TOKENS  # 675_000
TOTAL_COST = MAIN_COST + CONT_COST + DIRECT_COST + WORKFLOW_COST  # 4.485


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _materialize_fixture(tmp_path: Path) -> Path:
    """Copy the static fixture tree into tmp_path/claude/projects/project,
    substituting __CWD__ and timestamp placeholders with fresh "now"-relative
    values so week/24h/48h window-based assertions are meaningful, then pin
    each file's mtime so ownership of the shared message id is deterministic
    (main must be ingested before its continuation, regardless of checkout
    order or filesystem mtime resolution). conftest's autouse _isolated_db
    fixture already points CLAUDE_DIR at tmp_path/claude for this same
    tmp_path, so nothing else needs to be configured.
    """
    repo_dir = tmp_path / "myrepo-project"
    repo_dir.mkdir()

    # Anchored to :30 of the current hour so +-10s offsets around each of
    # the "3h ago" / "2h ago" anchors never cross an hour boundary -- the
    # heatmap grid-vs-tokenGrid assertions below depend on each session
    # landing in exactly one local-hour bucket.
    now = datetime.now(tz=UTC).replace(minute=30, second=0, microsecond=0)
    main_anchor = now - timedelta(hours=3)
    cont_anchor = now - timedelta(hours=2)
    subs = {
        "__CWD__": str(repo_dir),
        "__T_MAIN_1__": _iso(main_anchor),
        "__T_MAIN_2__": _iso(main_anchor + timedelta(seconds=5)),
        "__T_MAIN_3__": _iso(main_anchor + timedelta(seconds=10)),
        "__T_CONT_1__": _iso(cont_anchor),
        "__T_CONT_2__": _iso(cont_anchor + timedelta(seconds=5)),
        "__T_CONT_3__": _iso(cont_anchor + timedelta(seconds=10)),
        "__T_DIRECT_1__": _iso(main_anchor + timedelta(seconds=1)),
        "__T_DIRECT_2__": _iso(main_anchor + timedelta(seconds=6)),
        "__T_WORKFLOW_1__": _iso(main_anchor + timedelta(seconds=2)),
        "__T_WORKFLOW_2__": _iso(main_anchor + timedelta(seconds=7)),
    }

    dst_root = tmp_path / "claude" / "projects" / "project"
    for src in FIXTURE_ROOT.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(FIXTURE_ROOT)
        dst = dst_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text()
        for key, val in subs.items():
            text = text.replace(key, val)
        dst.write_text(text)

    epoch = time.time()
    main_file = dst_root / "11111111-1111-1111-1111-111111111111.jsonl"
    cont_file = dst_root / "22222222-2222-2222-2222-222222222222.jsonl"
    session_dir = dst_root / "11111111-1111-1111-1111-111111111111"
    direct_file = session_dir / "subagents" / "agent-adirect001.jsonl"
    workflow_file = (
        session_dir / "subagents" / "workflows" / "wf_test001" / "agent-aworkflow01.jsonl"
    )
    # Main must be the OLDEST file so it claims "shared-msg-001" first.
    os.utime(main_file, (epoch - 100, epoch - 100))
    os.utime(direct_file, (epoch - 90, epoch - 90))
    os.utime(workflow_file, (epoch - 80, epoch - 80))
    os.utime(cont_file, (epoch - 50, epoch - 50))

    return repo_dir


def _reset_db() -> None:
    import app.db as db_mod

    db_mod._engine = None
    db_mod._sessionmaker = None


@pytest.mark.asyncio
async def test_session_tokens_are_exact_deduped_sum(tmp_path: Path) -> None:
    _materialize_fixture(tmp_path)
    _reset_db()

    from app.models.message_ledger import MessageLedgerRow
    from app.models.session_summary import SessionSummaryRow
    from app.models.subagent_call import SubagentCallRow
    from app.services.ingest import ingest_all

    result = await ingest_all()
    assert result["new"] >= 4  # main + continuation + direct + workflow

    from app.db import _sessionmaker

    async with _sessionmaker() as session:
        main = await session.get(SessionSummaryRow, "11111111-1111-1111-1111-111111111111")
        cont = await session.get(SessionSummaryRow, "22222222-2222-2222-2222-222222222222")
        sc_rows = (await session.execute(select(SubagentCallRow))).scalars().all()
        ledger_rows = (await session.execute(select(MessageLedgerRow))).scalars().all()

    assert main is not None
    assert main.tokens == MAIN_TOKENS
    assert main.cost == pytest.approx(MAIN_COST, abs=0.001)

    assert cont is not None
    # shared-msg-001 (150_000 tok) was already claimed by main (older
    # mtime -> ingested first) -- only cont-msg-003 remains for continuation.
    assert cont.tokens == CONT_TOKENS
    assert cont.cost == pytest.approx(CONT_COST, abs=0.001)

    assert len(sc_rows) == 2
    by_type = {r.agent_type: r for r in sc_rows}
    assert by_type["general-purpose"].tokens == DIRECT_TOKENS
    assert by_type["general-purpose"].cost == pytest.approx(DIRECT_COST, abs=0.001)
    assert by_type["workflow-subagent"].tokens == WORKFLOW_TOKENS
    assert by_type["workflow-subagent"].cost == pytest.approx(WORKFLOW_COST, abs=0.001)

    # Every unique message id across all 4 files is claimed exactly once,
    # and the shared one is owned by the chronologically-original file.
    assert {r.message_id for r in ledger_rows} == {
        "shared-msg-001", "main-msg-002", "cont-msg-003", "direct-msg-004", "workflow-msg-005",
    }
    shared = next(r for r in ledger_rows if r.message_id == "shared-msg-001")
    assert shared.file_path.endswith("11111111-1111-1111-1111-111111111111.jsonl")


@pytest.mark.asyncio
async def test_dashboard_repo_cost_and_heatmap_include_subagents(tmp_path: Path) -> None:
    _materialize_fixture(tmp_path)
    _reset_db()

    from app.services.ingest import ingest_all

    await ingest_all()

    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        dash = (await c.get("/api/stats/dashboard")).json()
        cost = (await c.get("/api/cost", params={"days": 7})).json()
        heat = (await c.get("/api/stats/heatmap")).json()
        sessions = (await c.get("/api/sessions")).json()

    # ---- /stats/dashboard ----
    assert dash["tokens"]["thisWeek"] == TOTAL_TOKENS
    assert dash["cost"]["thisWeek"] == pytest.approx(TOTAL_COST, abs=0.01)
    # Both sessions (3h/2h ago) and their subagent calls fall inside the
    # last 24h sparkline window.
    assert sum(dash["tokens"]["spark"]) == TOTAL_TOKENS

    # ---- /api/cost ----
    assert cost["totalTokens"] == TOTAL_TOKENS
    assert cost["totalCost"] == pytest.approx(TOTAL_COST, abs=0.01)
    by_agent = {a["agent"]: a for a in cost["byAgent"]}
    assert by_agent["general-purpose"]["tokens"] == DIRECT_TOKENS
    assert by_agent["workflow-subagent"]["tokens"] == WORKFLOW_TOKENS
    by_repo = {r["repo"]: r for r in cost["byRepo"]}
    assert by_repo["myrepo-project"]["tokens"] == TOTAL_TOKENS

    # ---- repo_stats (feeds /api/repos) ----
    from app.services.repo_stats import fetch_real_stats

    per_repo = await fetch_real_stats()
    assert per_repo["myrepo-project"].tokens_week == TOTAL_TOKENS
    assert per_repo["myrepo-project"].cost_week == pytest.approx(TOTAL_COST, abs=0.01)

    # ---- heatmap ----
    # tokenGrid sums to the same deduped total (subagent/workflow hourly
    # buckets included, real spend wherever it came from). The plain
    # session-count grid only counts the two REAL sessions (main +
    # continuation) -- a subagent call is not a session of its own.
    token_total = sum(sum(day) for day in heat["tokenGrid"])
    assert token_total == TOTAL_TOKENS
    grid_total = sum(sum(day) for day in heat["grid"])
    assert grid_total == 2

    # ---- /api/sessions: a session's total includes its subagents ----
    by_id = {s["id"]: s for s in sessions}
    assert by_id["11111111"]["tokens"] == MAIN_TOKENS + DIRECT_TOKENS + WORKFLOW_TOKENS
    assert by_id["22222222"]["tokens"] == CONT_TOKENS


@pytest.mark.asyncio
async def test_reingest_is_idempotent(tmp_path: Path) -> None:
    _materialize_fixture(tmp_path)
    _reset_db()

    from app.models.message_ledger import MessageLedgerRow
    from app.models.session_summary import SessionSummaryRow
    from app.models.subagent_call import SubagentCallRow
    from app.services.ingest import ingest_all

    first = await ingest_all()

    from app.db import _sessionmaker

    async with _sessionmaker() as session:
        main_before = await session.get(SessionSummaryRow, "11111111-1111-1111-1111-111111111111")
        tokens_before = main_before.tokens
        sc_count_before = len((await session.execute(select(SubagentCallRow))).scalars().all())
        ledger_count_before = len((await session.execute(select(MessageLedgerRow))).scalars().all())

    second = await ingest_all()
    assert second["new"] == 0
    assert second["updated"] == 0
    assert second["skipped"] >= first["new"]

    async with _sessionmaker() as session:
        main_after = await session.get(SessionSummaryRow, "11111111-1111-1111-1111-111111111111")
        sc_count_after = len((await session.execute(select(SubagentCallRow))).scalars().all())
        ledger_count_after = len((await session.execute(select(MessageLedgerRow))).scalars().all())

    assert main_after.tokens == tokens_before
    assert sc_count_after == sc_count_before
    assert ledger_count_after == ledger_count_before


@pytest.mark.asyncio
async def test_version_bump_self_heals_stale_db(tmp_path: Path) -> None:
    """A DB populated by the OLD (pre-fix) ingest logic -- workflow-agent
    tokens never made it in, so the session looks badly under-counted --
    must correct itself automatically on the next ingest, once, without a
    manual `tracker rebuild`.
    """
    _materialize_fixture(tmp_path)
    _reset_db()

    from app.db import init_db
    from app.models.ingest_meta import SINGLETON_ID, IngestMetaRow
    from app.models.session_summary import SessionSummaryRow

    await init_db()
    # Import AFTER init_db(): _reset_db() cleared the module global, and a
    # from-import before init_db() would capture None.
    from app.db import _sessionmaker
    now = datetime.now(tz=UTC)
    async with _sessionmaker() as session:
        session.add(SessionSummaryRow(
            session_id="11111111-1111-1111-1111-111111111111",
            repo="myrepo-project",
            started_at=now - timedelta(hours=3),
            last_event_at=now - timedelta(hours=3),
            status="completed",
            tokens=999,  # the old bug's wrong number
            cost=9.99,
            edits=0,
            file_path="stale-old-ingest.jsonl",
            file_mtime=1.0,
        ))
        session.add(IngestMetaRow(id=SINGLETON_ID, version=1))  # behind INGEST_VERSION
        await session.commit()

    from app.services.ingest import INGEST_VERSION, ingest_all

    await ingest_all()

    async with _sessionmaker() as session:
        main = await session.get(SessionSummaryRow, "11111111-1111-1111-1111-111111111111")
        meta = await session.get(IngestMetaRow, SINGLETON_ID)

    assert main is not None
    assert main.tokens == MAIN_TOKENS  # corrected by the forced rebuild
    assert meta is not None
    assert meta.version == INGEST_VERSION
