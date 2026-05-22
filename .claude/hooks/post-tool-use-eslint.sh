#!/usr/bin/env bash
# Auto-lint .js/.jsx/.mjs/.cjs files after Edit/Write in claude-tracker.
# File-extension filtering is now handled by the `if:` matcher in settings.json
# (since v2.1.85). This script just lints whatever the hook passes through.
#
# Falls back silently if eslint isn't available; never fails the tool call.
#
# v2.1.133 effort gating:
#   When CLAUDE_EFFORT=low, pass --quiet to eslint so it reports errors
#   only (no warnings). At medium/high, lint everything. This keeps
#   low-effort sessions snappy without losing real failures.
#
# v2.1.141-style terminalSequence:
#   On lint failure (non-zero exit code from eslint itself), flash the
#   terminal via a /dev/tty bell + OSC window-title. /dev/tty bypasses
#   Claude's stdio capture so the visible feedback to Claude is unchanged.

set -u

FILE="${CLAUDE_TOOL_USE_INPUT_FILE_PATH:-}"
PROJECT="${CLAUDE_PROJECT_DIR:-$HOME/Documents/Personal/claude-tracker}"
EFFORT="${CLAUDE_EFFORT:-medium}"

# Safety net: skip if the file isn't inside the project (e.g. sibling-repo edits).
# The `if:` matcher in settings.json should already filter, but defense in depth.
case "$FILE" in
  "$PROJECT"/*) ;;
  *) exit 0 ;;
esac

cd "$PROJECT" || exit 0

# Build per-effort flag list. Low effort skips warnings; everything else
# runs the default ruleset.
EXTRA_FLAGS=()
case "$EFFORT" in
  low) EXTRA_FLAGS+=("--quiet") ;;
  *) ;;
esac

# Run eslint with the appropriate runner. Capture exit code so we can
# decide whether to flash the terminal.
LINT_EXIT=0
LINT_OUT=""
if [ -x "node_modules/.bin/eslint" ]; then
  LINT_OUT=$(node_modules/.bin/eslint --fix --no-eslintrc -c eslint.config.js "${EXTRA_FLAGS[@]}" "$FILE" 2>&1)
  LINT_EXIT=$?
elif command -v pnpm >/dev/null 2>&1 && [ -f "package.json" ]; then
  LINT_OUT=$(pnpm exec eslint --fix "${EXTRA_FLAGS[@]}" "$FILE" 2>&1)
  LINT_EXIT=$?
elif command -v npx >/dev/null 2>&1; then
  LINT_OUT=$(npx --no-install eslint --fix "${EXTRA_FLAGS[@]}" "$FILE" 2>&1)
  LINT_EXIT=$?
fi

# Always print first 30 lines of output (so Claude sees what failed)
printf '%s\n' "$LINT_OUT" | head -30

# Flash the terminal on lint failure. /dev/tty bypasses Claude's stdio.
if [ "$LINT_EXIT" -ne 0 ] && [ -w /dev/tty ]; then
  printf '\a\033]0;claude-tracker: lint failed\007' > /dev/tty 2>/dev/null || true
fi

# Never fail the tool call — eslint errors are fed back as text instead.
exit 0
