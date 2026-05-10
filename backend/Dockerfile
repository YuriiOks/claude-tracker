# syntax=docker/dockerfile:1.9
# claude-tracker backend — Python 3.13 + uv + FastAPI

# ---- Stage 1: build venv with uv ---------------------------------------------
FROM ghcr.io/astral-sh/uv:0.5.14-python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# Install dependencies first (cached layer if pyproject/lock unchanged)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra dev --no-install-project

# Now install the project itself
COPY app ./app
COPY tests ./tests
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra dev


# ---- Stage 2: slim runtime ---------------------------------------------------
FROM python:3.13.1-slim-bookworm AS runtime

# git: needed by repo_scanner / diffs / integrations subprocess calls
# tini: clean PID 1 signal handling for uvicorn under Compose
RUN apt-get update \
    && apt-get install -y --no-install-recommends git tini ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HOST=0.0.0.0 \
    PORT=8765

WORKDIR /app

# Copy the prebuilt venv and the app source from the builder stage
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/app ./app
COPY pyproject.toml uv.lock ./

# Cache directory for SQLite — mounted as a named volume in compose
RUN mkdir -p /app/.cache

# Non-root runtime user
RUN groupadd --system tracker && useradd --system --gid tracker --home /app tracker \
    && chown -R tracker:tracker /app
USER tracker

EXPOSE 8765

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
