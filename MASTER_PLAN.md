# Claude Tracker — Master Plan

> Living document. Reflects the full trajectory from today's React-only mock to a deployable single-user platform that observes Claude Code activity end-to-end.
> Last updated: 2026-05-10.

---

## 1. Vision

Claude Tracker is a personal observability dashboard for one developer's Claude Code usage across all repos. It answers, at a glance:

- **What is Claude doing right now?** (live tool calls, agent delegation, permission prompts)
- **What did Claude do today / this week?** (sessions, costs, edits, ticket linkage)
- **What is Claude configured with?** (agents, skills, commands, rules, hooks, plugins, MCP servers — global and per-repo)
- **What is breaking?** (denied permissions, failed tool calls, runaway costs)

It is a *meta-tool*: the data it consumes is a side-effect of using Claude Code itself.

It is intentionally **single-user, local-first**. No cloud, no auth, no multi-tenancy. Runs on the same laptop as Claude Code.

---

## 2. Today (baseline)

| Layer | Status |
|---|---|
| Frontend | Vite 8 + React 19 + vanilla CSS, dark/light themes, 11 routes, Tweaks panel — working |
| Components | Sidebar, Dashboard, Repos (grid/list/board), Sessions, Live, Agents, Graph, Heatmap, Cost, Permissions, Plugins, Diff, RepoDetail, AgentDetail — working |
| Data | 100 % mocked in `src/data.js` — REPOS, GLOBAL, AGENT_META, SESSIONS, LIVE_EVENTS_*, PERMISSIONS_DETAIL, DIFF_SAMPLE, FILE_SIZES |
| Live stream | Synthetic (`useLiveStream` cycles `LIVE_EVENTS_FUTURE`) |
| Backend | Does not exist |
| Tests | None |
| Deploy | Local `vite dev` only |

---

## 3. Target (north star)

A two-process local platform:

```
┌─────────────────────┐         ┌──────────────────────────┐
│  Vite + React       │  /api   │  FastAPI (Python 3.11+)  │
│  http://:5173       │ ──────► │  http://:8000            │
│                     │  /ws    │                          │
│  data.js shape      │ ◄────── │  Pydantic schemas        │
│  (contract)         │         │  SQLAlchemy + SQLite     │
└─────────────────────┘         │  watchfiles → WebSocket  │
                                └────────────┬─────────────┘
                                             │ reads
                                             ▼
                            ┌──────────────────────────────────┐
                            │  ~/.claude/projects/**/*.jsonl   │
                            │  ~/.claude/plugins/*.json        │
                            │  ~/.claude/cost-tracker.log      │
                            │  <repo>/.claude/{agents,skills,  │
                            │      commands,rules,hooks}/      │
                            │  git symbolic-ref <repo>         │
                            │  (optional) Linear, Langfuse,    │
                            │             GitHub APIs          │
                            └──────────────────────────────────┘
```

Acceptance: every existing UI route renders real data; the live panel updates as Claude is used in any tracked repo; toggling `VITE_USE_MOCKS=1` restores the all-mock demo experience for screenshots / showcase.

---

## 4. Roadmap (phased)

Each phase is independently shippable. Don't skip ahead.

### Phase A — Python backend (≈3.5 days)
Detailed plan: `~/.claude/plans/develop-a-plan-of-typed-babbage.md`.

Sub-phases A1–A5:
- **A1 Scaffold** — FastAPI + uv, Vite proxy, health endpoint.
- **A2 Schemas + repo scanner** — Pydantic models mirror `data.js` exactly; `/api/repos`, `/api/global`, `/api/permissions`, `/api/plugins`.
- **A3 JSONL ingest + cache** — SQLAlchemy/SQLite, `tracker ingest` CLI, `/api/sessions`, `/api/agents`, `/api/cost`, `/api/diffs/recent`.
- **A4 Live WebSocket** — `watchfiles` tailer + asyncio pubsub Hub at `WS /ws/live`.
- **A5 Frontend wiring** — `src/api.js` hooks replace `data.js` imports; mocks gated behind `VITE_USE_MOCKS=1`.

**Exit criterion:** all 11 frontend routes render real data; mock-mode demo still works.

### Phase B — Hardening & polish (≈2 days)
- **B1** Test coverage: parser unit tests with anonymized JSONL fixture; route integration tests via `httpx.AsyncClient`; frontend smoke tests with Vitest + React Testing Library (first tests in this repo).
- **B2** Error UI: every fetch hook in `src/api.js` surfaces loading + error states; one shared `<ErrorBoundary>` for crashes.
- **B3** Empty states: every page handles "no repos configured", "no sessions yet", "WS disconnected" cleanly.
- **B4** Performance: pagination on `/api/sessions` (default 50, cursor-based); virtualize Sessions table if > 200 rows.
- **B5** Logging: structured JSON logs from FastAPI to `backend/.cache/tracker.log`; rotating file handler.

### Phase C — Real integrations (≈2 days, optional)
- **C1** Linear: resolve ticket from branch name (`feat/ACM-026-…` → `ACM-026`), attach title to `Repo.activeTask`, link out from Sessions.
- **C2** Langfuse: backfill cost from traces matched on session id; reconcile against `cost-tracker.log`.
- **C3** GitHub: latest PR per branch via `gh` CLI (no API token needed); show PR status badge on RepoDetail.
- **C4** Sentry / errors: pull error counts per repo if Sentry DSN configured.

### Phase D — Distribution (≈1 day, optional)
- **D1** One-command launch: `Makefile` or `task` runner to start backend + frontend together (`task dev` → concurrent `uv run uvicorn ...` and `pnpm dev`).
- **D2** Single-binary build: `pyinstaller` or `pex` for the backend; Vite production build bundled into FastAPI's `StaticFiles`. Result: one `tracker` binary that serves the SPA + API on a single port.
- **D3** macOS launchd plist so the backend auto-starts at login (opt-in).
- **D4** `README.md` install steps for someone else cloning the repo.

### Phase E — Multi-device sync (≈3 days, *if* a real need emerges)
Don't build until needed. If Claude is used on a second machine and a unified view is wanted:
- **E1** SQLite → Litestream replication to S3-compatible store.
- **E2** `tracker pull` CLI imports another machine's snapshot.
- **E3** Repo dimension `host` added to schema; UI filter.

### Phase F — Open source (≈1 day, *if* publication is decided)
- **F1** Strip user-specific paths and tokens from `CLAUDE.md` / `README.md`.
- **F2** Add `LICENSE` (MIT recommended).
- **F3** Public README with screenshot, install, demo gif.
- **F4** Docker compose option for non-mac users.

---

## 5. Architecture decisions (locked)

| Decision | Choice | Why |
|---|---|---|
| Backend framework | **FastAPI** | Async, Pydantic-native, free OpenAPI, first-class WebSocket. |
| Schema source of truth | **`src/data.js`** | The contract. Backend mirrors it; never reshape. |
| Cache | **SQLite via SQLAlchemy 2.0 (async)** | Single-file, no service to run. Sufficient at single-user scale. |
| Live tail | **watchfiles** | Rust-backed, async, cross-platform. |
| Python deps | **uv + pyproject.toml** | Lockfile + speed. |
| Frontend deps | **npm/pnpm + vanilla CSS** | Existing rule. No CSS framework. |
| Language | **JavaScript + JSX** (not TS) | CLAUDE.md rule until design solidifies. |
| Auth | **None** | Localhost-only binding (`127.0.0.1`). |
| State management | **React `useState`** | No Redux / Zustand needed at current scope. |
| Routing | **`useState({page})` switch in `App.jsx`** | Fine until ≥ 3 routes share state (CLAUDE.md). |

Reversible later if needed: state mgmt, routing, deployment shape.

Locked for the foreseeable future: schema contract, vanilla CSS, no TS.

---

## 6. Repository layout (target)

```
claude-tracker/
├── README.md
├── CLAUDE.md
├── AGENTS.md → CLAUDE.md
├── MASTER_PLAN.md          ← this file
├── package.json
├── vite.config.js          (+ /api & /ws proxy)
├── eslint.config.js
├── index.html
├── public/
├── src/
│   ├── App.jsx
│   ├── api.js              ← Phase A5: hooks replacing data.js
│   ├── data.js             ← stays, gated by VITE_USE_MOCKS
│   ├── components/
│   ├── styles.css
│   └── ...
├── backend/                ← Phase A
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── README.md
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── schemas/
│   │   ├── models/
│   │   ├── routers/
│   │   ├── services/
│   │   └── cli.py
│   └── tests/
├── docs/                   ← HTML docs (Thariq pattern)
├── chats/
└── project/                ← original handoff materials
```

---

## 7. Schemas — the contract

The backend NEVER reshapes data. Pydantic models use `Field(alias="…")` to match `data.js` keys exactly.

| `data.js` export | Pydantic model | Endpoint |
|---|---|---|
| `REPOS[]` | `Repo` | `GET /api/repos`, `GET /api/repos/{id}` |
| `GLOBAL` | `GlobalScope` | `GET /api/global` |
| `AGENT_META` | `dict[str, AgentMeta]` | `GET /api/agents`, `GET /api/agents/{name}` |
| `SESSIONS[]` | `Session` | `GET /api/sessions?repo=&limit=` |
| `LIVE_EVENTS_SEED` + `_FUTURE` | `LiveEvent` | `GET /api/live/recent`, `WS /ws/live` |
| `PERMISSIONS_DETAIL` | `PermissionsDetail` | `GET /api/permissions` |
| `DIFF_SAMPLE` | `Diff` | `GET /api/diffs/recent` |
| `FILE_SIZES` | `FileSizes` | embedded in `/api/global` and `/api/repos/{id}` |

**Frontend rule:** components import from `src/api.js`, never from `src/data.js` directly (after Phase A5). The mock fallback is opaque to consumers.

---

## 8. Live event taxonomy

Events from JSONL → WebSocket map to one of these `kind` values. Every consumer (live panel, graph, heatmap) discriminates on `kind`.

| kind | Source line type | Payload fields |
|---|---|---|
| `agent_start` | top-level `assistant` with `subagent_type` set | `agent`, `msg` (first text) |
| `tool` | `tool_use` | `tool`, `target` (file path or arg summary) |
| `delegate` | `Task` tool_use | `from`, `to`, `msg` |
| `skill` | `Skill` tool_use | `skill`, `msg` |
| `permission` | `system` subtype `permission_*` | `level` (allow/deny/ask), `action`, `granted` |
| `command` | user message starting with `/` | `cmd`, `msg` |

Unknown line types are logged and skipped — never raise.

---

## 9. Verification matrix (end-to-end)

After each phase, this command set must pass:

```bash
# backend
cd backend && uv sync && uv run pytest -q
uv run uvicorn app.main:app --reload &       # :8000
uv run tracker ingest                         # populate cache
curl -s localhost:8000/api/health             # {"ok": true}
curl -s localhost:8000/api/repos | jq 'length'

# frontend
cd .. && pnpm install && pnpm lint && pnpm build
pnpm dev &                                    # :5173 with /api,/ws proxy

# manual
open http://localhost:5173                    # all 11 routes load
# trigger a real claude session in any tracked repo
# → live panel emits real events within ≤2s

# mock fallback
VITE_USE_MOCKS=1 pnpm dev                     # demo mode unchanged
```

Any failure halts the phase.

---

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| JSONL format changes between Claude versions | Parser tolerates unknown `type` values; one fixture per observed version under `backend/tests/fixtures/`. |
| Large JSONL files (100s of MB) on first ingest | Stream-parse line-by-line; never load whole file. SQLite UPSERT keyed on `session_id`. |
| `watchfiles` debounce misses fast bursts | Combine FS watch with periodic poll (every 30s) for missed-event reconciliation. |
| WebSocket disconnect during a live session | Frontend backoff + replay last 60 events from `/api/live/recent` on reconnect. |
| Cost data drift between `cost-tracker.log` and Langfuse | `cost-tracker.log` is source of truth; Langfuse is enrichment. Document in `backend/README.md`. |
| Schema drift between `data.js` and Pydantic | Snapshot test compares `Repo.model_dump(by_alias=True)` against a hand-typed JS-shape fixture. CI fails on mismatch. |
| Secrets accidentally committed | `backend/.env` in `.gitignore`; `gh secret-scan` in pre-commit hook (Phase B). |

---

## 11. Out of scope

Will not build unless explicitly asked:

- Multi-user / multi-tenant.
- SSO / auth / RBAC.
- Hosting on the public internet.
- Mobile app.
- Slack/email/push alerts.
- Editing Claude config from the UI (the dashboard is read-only by design).
- Recording/replay of Claude sessions beyond what JSONL already gives us.
- Cross-tool comparison (Cursor, Cline, Aider) — Claude-only.

---

## 12. Cadence & review

- **Daily during active dev:** end-of-day commit, update `## 2. Today` row by row as it shifts.
- **End of each phase:** tick exit criterion, append a one-liner to a `## Changelog` section (TBD), tag a release if Phase D shipped.
- **Master-plan review:** monthly. Trim what didn't ship; archive what did.

---

## 13. Quick reference

- Sub-plan (Phase A detail): `~/.claude/plans/develop-a-plan-of-typed-babbage.md`
- Frontend contract: `src/data.js`
- Project rules: `CLAUDE.md`
- HTML doc generator: `skill: html-docs` + `.claude/rules/html-first.md`
- Original design materials: `project/`, `chats/`

---

*This is a plan, not a contract. When reality and the plan disagree, update the plan.*
