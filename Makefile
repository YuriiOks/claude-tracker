# claude-tracker — convenience targets.
# All Python work goes through uv; all frontend through npm.

UV := $(HOME)/.local/bin/uv
BACKEND_DIR := backend

# LAN mode (see backend/app/security.py + CLAUDE.md "Phone / LAN access").
# Off by default -- everything below is a no-op unless overridden by
# `dev-lan` / `docker-up-lan`, or by hand: `LAN_MODE=1 make dev`.
LAN_MODE ?= 0
LAN_BIND ?=

.PHONY: help install dev dev-lan backend frontend ingest rebuild test test-backend lint build clean \
        pair docker-up docker-up-lan docker-down docker-logs docker-rebuild docker-ingest docker-pair \
        docker-test docker-prod docker-prune

help:
	@echo "Bare-metal targets:"
	@echo "  install        Install backend (uv sync) and frontend (npm install) deps."
	@echo "  dev            Start backend (:8765) and frontend (:5173) concurrently."
	@echo "  dev-lan        Same as dev, with the frontend published on the LAN."
	@echo "  backend        Start only the FastAPI backend on :8765 with --reload."
	@echo "  frontend       Start only the Vite dev server on :5173."
	@echo "  ingest         Walk ~/.claude/projects/**/*.jsonl and populate SQLite."
	@echo "  rebuild        Drop cache and re-ingest everything."
	@echo "  pair           Print a phone-pairing link (needed once LAN mode is on)."
	@echo "  test           Run backend pytest suite."
	@echo "  lint           Run ruff (backend) and eslint (frontend)."
	@echo "  build          Build the production frontend bundle into dist/."
	@echo "  clean          Remove caches, dist, .venv."
	@echo ""
	@echo "Docker targets (uses .env.docker, ports 47820/47821):"
	@echo "  docker-up      Build and start backend + frontend in dev mode (detached)."
	@echo "  docker-up-lan  Same as docker-up, with the frontend published on the LAN."
	@echo "  docker-down    Stop and remove the stack (keeps the cache volume)."
	@echo "  docker-logs    Tail logs from both services."
	@echo "  docker-rebuild Force-rebuild images, no cache, then up."
	@echo "  docker-ingest  Run \`tracker ingest\` inside the running backend container."
	@echo "  docker-pair    Print a phone-pairing link (needed once LAN mode is on)."
	@echo "  docker-test    Run pytest inside a one-shot backend container."
	@echo "  docker-prod    Build and start the nginx-served prod frontend."
	@echo "  docker-prune   docker-down + remove volumes (DESTRUCTIVE: drops the cache)."

install:
	cd $(BACKEND_DIR) && $(UV) sync --extra dev
	npm install

dev:
	@echo "Starting backend :8765 and frontend :5173 (Ctrl-C to stop both)."; \
	 echo "  → local:   http://localhost:5173"; \
	 if [ "$(LAN_MODE)" = "1" ] || [ "$(LAN_MODE)" = "true" ]; then \
	   LAN_IP=$$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "?"); \
	   echo "  → network: http://$$LAN_IP:5173  ← open on phone (run \`make pair\` for a token link)"; \
	 fi
	@trap 'kill 0' EXIT; \
	  ( cd $(BACKEND_DIR) && LAN_MODE=$(LAN_MODE) $(UV) run uvicorn app.main:app --reload --port 8765 ) & \
	  LAN_MODE=$(LAN_MODE) npm run dev & \
	  wait

dev-lan:
	@$(MAKE) dev LAN_MODE=1

backend:
	cd $(BACKEND_DIR) && $(UV) run uvicorn app.main:app --reload --port 8765

frontend:
	npm run dev

ingest:
	cd $(BACKEND_DIR) && $(UV) run tracker ingest

rebuild:
	cd $(BACKEND_DIR) && $(UV) run tracker rebuild

pair:
	@LAN_IP=$$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "?"); \
	 TOKEN=$$(cd $(BACKEND_DIR) && $(UV) run tracker pair); \
	 echo "http://$$LAN_IP:5173/?pair=$$TOKEN"

test test-backend:
	cd $(BACKEND_DIR) && $(UV) run pytest -q

lint:
	cd $(BACKEND_DIR) && $(UV) run ruff check app tests
	npm run lint || true

build:
	npm run build

clean:
	rm -rf dist node_modules/.vite
	rm -rf $(BACKEND_DIR)/.venv $(BACKEND_DIR)/.cache $(BACKEND_DIR)/.pytest_cache

# ─── Docker ──────────────────────────────────────────────────────────────────
COMPOSE := docker compose

docker-up:
	@test -f .env.docker || (echo "→ .env.docker not found. Copy .env.docker.example and edit REPO_ROOTS for your machine." && exit 1)
	LAN_MODE=$(LAN_MODE) LAN_BIND=$(LAN_BIND) $(COMPOSE) up -d --build
	@echo "→ local:   http://localhost:47820"; \
	 if [ "$(LAN_MODE)" = "1" ] || [ "$(LAN_MODE)" = "true" ]; then \
	   LAN_IP=$$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "?"); \
	   echo "→ network: http://$$LAN_IP:47820  ← open on phone (run \`make docker-pair\` for a token link)"; \
	 fi

docker-up-lan:
	@$(MAKE) docker-up LAN_MODE=1 LAN_BIND=0.0.0.0

docker-down:
	$(COMPOSE) down

docker-logs:
	$(COMPOSE) logs -f --tail=200

docker-rebuild:
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d

docker-ingest:
	$(COMPOSE) exec backend tracker ingest

docker-pair:
	@LAN_IP=$$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "?"); \
	 TOKEN=$$($(COMPOSE) exec -T backend tracker pair); \
	 echo "http://$$LAN_IP:47820/?pair=$$TOKEN"

docker-test:
	$(COMPOSE) run --rm --no-deps backend pytest -q

docker-prod:
	LAN_MODE=$(LAN_MODE) LAN_BIND=$(LAN_BIND) $(COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml up -d --build
	@echo "→ prod frontend: http://localhost:47820"

docker-prune:
	$(COMPOSE) down -v
