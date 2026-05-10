# claude-tracker — convenience targets.
# All Python work goes through uv; all frontend through npm.

UV := $(HOME)/.local/bin/uv
BACKEND_DIR := backend

.PHONY: help install dev backend frontend ingest rebuild test test-backend lint build clean

help:
	@echo "Targets:"
	@echo "  install        Install backend (uv sync) and frontend (npm install) deps."
	@echo "  dev            Start backend (:8765) and frontend (:5173) concurrently."
	@echo "  backend        Start only the FastAPI backend on :8765 with --reload."
	@echo "  frontend       Start only the Vite dev server on :5173."
	@echo "  ingest         Walk ~/.claude/projects/**/*.jsonl and populate SQLite."
	@echo "  rebuild        Drop cache and re-ingest everything."
	@echo "  test           Run backend pytest suite."
	@echo "  lint           Run ruff (backend) and eslint (frontend)."
	@echo "  build          Build the production frontend bundle into dist/."
	@echo "  clean          Remove caches, dist, .venv."

install:
	cd $(BACKEND_DIR) && $(UV) sync --extra dev
	npm install

dev:
	@echo "Starting backend on :8765 and frontend on :5173 (Ctrl-C to stop both)."
	@trap 'kill 0' EXIT; \
	  ( cd $(BACKEND_DIR) && $(UV) run uvicorn app.main:app --reload --port 8765 ) & \
	  npm run dev & \
	  wait

backend:
	cd $(BACKEND_DIR) && $(UV) run uvicorn app.main:app --reload --port 8765

frontend:
	npm run dev

ingest:
	cd $(BACKEND_DIR) && $(UV) run tracker ingest

rebuild:
	cd $(BACKEND_DIR) && $(UV) run tracker rebuild

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
