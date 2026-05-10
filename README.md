# claude-tracker

Personal dashboard for visualizing Claude Code activity across repos. Live sessions, per-repo summaries, agent/skill/command inventories, plugin & MCP usage, permissions audit, cost & tokens, delegation graph, recent diffs.

## Stack

- **Frontend**: React 19 + Vite 8, vanilla CSS, dual dark/light theme (Fira Code + Inter)
- **Backend**: FastAPI + SQLAlchemy + aiosqlite, reads `~/.claude/projects/**/*.jsonl` and per-repo `.claude/` folders
- **Infrastructure**: Docker Compose, ports 47820 (frontend) / 47821 (backend)

## Quick start — Docker (recommended)

```bash
cp .env.docker.example .env.docker
# Edit REPO_ROOTS to point at your tracked repos
make docker-up
```

Open http://localhost:47820 — health: http://localhost:47821/api/health

## Quick start — bare-metal

```bash
# Backend (terminal 1)
cd backend
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload --port 8765
uv run tracker ingest    # populate SQLite cache from JSONL transcripts

# Frontend (terminal 2)
npm install
npm run dev              # → http://localhost:5173
```

## Project layout

| Path | Purpose |
|---|---|
| `src/` | React app (App.jsx single-file router, components/, data.js mock contract, styles.css) |
| `backend/app/` | FastAPI (routers/, services/, schemas/, models/) |
| `docker/` | nginx config for production frontend |
| `docs/` | Generated HTML documentation (audit reports, design docs) |
| `.claude/` | Project-local agents, skills, commands, rules |

## Key make targets

```bash
make help              # list all targets
make dev               # bare-metal: backend + frontend concurrently
make docker-up         # docker compose up -d
make docker-logs
make docker-rebuild
make ingest            # populate SQLite cache (bare-metal)
make docker-ingest     # same, in container
make lint              # eslint + ruff
make test              # backend pytest + frontend lint
```

## Documentation

Generated HTML docs live in `docs/`. Open with `open docs/<slug>.html` — self-contained, no server needed.

See also:
- `CLAUDE.md` — project intent, rules, gotchas for Claude Code sessions
- `AGENTS.md` — same content, for Codex/Cursor/Gemini compatibility
- `MASTER_PLAN.md` — full implementation roadmap
- `backend/README.md` — backend-specific setup
