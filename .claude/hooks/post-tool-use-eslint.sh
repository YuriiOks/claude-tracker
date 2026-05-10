#!/usr/bin/env bash
# Auto-lint .js/.jsx/.mjs files after Edit/Write in claude-tracker.
# Reads the edited file path from CLAUDE_TOOL_USE_INPUT_FILE_PATH (Claude Code env var).
# Falls back silently if eslint isn't available; never fails the tool call.

set -u

FILE="${CLAUDE_TOOL_USE_INPUT_FILE_PATH:-}"
PROJECT="${CLAUDE_PROJECT_DIR:-$HOME/Documents/Personal/claude-tracker}"

# Only lint JS/JSX in this project
case "$FILE" in
  *.js|*.jsx|*.mjs|*.cjs) ;;
  *) exit 0 ;;
esac

# Skip if file is outside the project (e.g., editing CLAUDE.md from a sibling repo)
case "$FILE" in
  "$PROJECT"/*) ;;
  *) exit 0 ;;
esac

cd "$PROJECT" || exit 0

if [ -x "node_modules/.bin/eslint" ]; then
  node_modules/.bin/eslint --fix --no-eslintrc -c eslint.config.js "$FILE" 2>&1 | head -30 || true
elif command -v pnpm >/dev/null 2>&1 && [ -f "package.json" ]; then
  pnpm exec eslint --fix "$FILE" 2>&1 | head -30 || true
elif command -v npx >/dev/null 2>&1; then
  npx --no-install eslint --fix "$FILE" 2>&1 | head -30 || true
fi

exit 0
