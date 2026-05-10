# claude-tracker-backend

Local FastAPI service that reads Claude Code's on-disk state (`~/.claude/projects/**/*.jsonl`, plugin caches, per-repo `.claude/` folders) and serves it through a JSON API + WebSocket whose schema mirrors `src/data.js` 1:1.

See `MASTER_PLAN.md` at the repo root for the full plan.

## Quick start

```bash
cd backend
uv sync                                          # install deps
cp .env.example .env                             # tweak REPO_ROOTS if needed
uv run uvicorn app.main:app --reload --port 8765 # :8765
uv run tracker ingest                            # populate SQLite cache
uv run pytest -q                                 # tests
```

Then in another terminal:

```bash
cd ..
pnpm dev                                         # :5173, /api and /ws proxied to :8765
```

## Endpoints

| Method | Path | Source |
|---|---|---|
| GET | `/api/health` | trivially `{"ok": true}` |
| GET | `/api/repos` | per-repo `.claude/` walk + git branch |
| GET | `/api/repos/{id}` | one repo with full inventory |
| GET | `/api/global` | `~/.claude/{settings,skills,plugins,agents,commands}` |
| GET | `/api/sessions` | aggregated JSONL summaries (cached) |
| GET | `/api/agents` | agent meta + delegate edges |
| GET | `/api/agents/{name}` | one agent |
| GET | `/api/permissions` | merged allow/deny/ask rules |
| GET | `/api/plugins` | `~/.claude/plugins/installed_plugins.json` passthrough |
| GET | `/api/cost` | rolled-up cost from `cost-tracker.log` |
| GET | `/api/diffs/recent` | latest Edit/Write paired with `git diff` |
| GET | `/api/live/recent` | last N live events (cold start) |
| WS | `/ws/live` | streamed live events from JSONL tail |

## Configuration

`.env` (gitignored):

```
CLAUDE_DIR=~/.claude
REPO_ROOTS=~/Desktop/jupus,~/Desktop/voice,~/Desktop/anita,~/Documents/Personal/claude-tracker
DB_PATH=./.cache/tracker.db
LOG_LEVEL=INFO
```

`REPO_ROOTS` is a comma-separated list of repo paths. The scanner reads `<repo>/.claude/` and runs `git symbolic-ref --short HEAD` for the branch.

## Layout

```
backend/
├── pyproject.toml
├── README.md
├── .env.example
├── app/
│   ├── main.py        # FastAPI factory, CORS, lifespan
│   ├── config.py      # Pydantic Settings
│   ├── db.py          # SQLAlchemy async engine
│   ├── schemas/       # Pydantic models — mirror data.js shape
│   ├── models/        # SQLAlchemy ORM (cache layer)
│   ├── routers/       # one file per /api section
│   ├── services/      # repo_scanner, jsonl_parser, live_stream, stats, …
│   └── cli.py         # `tracker ingest`, `tracker rebuild`
└── tests/
    ├── conftest.py
    └── fixtures/
```
