#!/usr/bin/env bash
# Auto-lint .py files after Edit/Write in claude-tracker (backend only).
# Mirrors post-tool-use-eslint.sh for the Python side.
# Reads the edited file path from CLAUDE_TOOL_USE_INPUT_FILE_PATH.
# Falls back silently if uv/ruff isn't available; never fails the tool call.

set -u

FILE="${CLAUDE_TOOL_USE_INPUT_FILE_PATH:-}"
PROJECT="${CLAUDE_PROJECT_DIR:-$HOME/Documents/Personal/claude-tracker}"
BACKEND="$PROJECT/backend"

case "$FILE" in
  *.py) ;;
  *) exit 0 ;;
esac

case "$FILE" in
  "$BACKEND"/*) ;;
  *) exit 0 ;;
esac

cd "$BACKEND" || exit 0

UV="${UV:-$HOME/.local/bin/uv}"
if [ -x "$UV" ]; then
  "$UV" run ruff check --fix "$FILE" 2>&1 | head -30 || true
elif command -v ruff >/dev/null 2>&1; then
  ruff check --fix "$FILE" 2>&1 | head -30 || true
fi

exit 0
