#!/usr/bin/env bash
# Auto-lint .js/.jsx/.mjs/.cjs files after Edit/Write in claude-tracker.
# File-extension filtering is now handled by the `if:` matcher in settings.json
# (since v2.1.85). This script just lints whatever the hook passes through.
#
# Falls back silently if eslint isn't available; never fails the tool call.

set -u

FILE="${CLAUDE_TOOL_USE_INPUT_FILE_PATH:-}"
PROJECT="${CLAUDE_PROJECT_DIR:-$HOME/Documents/Personal/claude-tracker}"

# Safety net: skip if the file isn't inside the project (e.g. sibling-repo edits).
# The `if:` matcher in settings.json should already filter, but defense in depth.
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
