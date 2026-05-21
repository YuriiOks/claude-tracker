#!/usr/bin/env bash
# Silently records non-zero Bash exits to a session-scoped candidate log.
# Paired with stop-draft-errors.sh, which surfaces clusters of >=2 failures
# as a draft ERRORS.md entry at the repo root.
#
# Reads PostToolUse stdin JSON. Always exits 0.
#
# Safe-by-design:
#   - skips non-Bash tool calls
#   - skips zero exit codes
#   - never blocks; never prints to stdout
#   - state lives in ~/.claude/state/errors-candidates/ (per repo + session)

set -u
INPUT=$(cat)

# Require jq; degrade silently if missing
command -v jq >/dev/null 2>&1 || exit 0

TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
[ "$TOOL" = "Bash" ] || exit 0

EXIT_CODE=$(printf '%s' "$INPUT" | jq -r '.tool_response.exit_code // .tool_response.code // empty' 2>/dev/null)
case "$EXIT_CODE" in
  ""|"0") exit 0 ;;
esac

COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -n "$COMMAND" ] || exit 0

# Normalize a "target" signature so retries of the same command coalesce.
# Recognised heads collapse to a stable key, e.g.:
#   "docker compose run app py.test app/ai/..."  -> "docker-compose-run-app"
#   "pytest -k foo tests/"                       -> "pytest"
#   "npm run lint"                               -> "npm-run"
TARGET=$(printf '%s' "$COMMAND" | awk '
  {
    for (i=1; i<=NF; i++) {
      if ($i ~ /^(pytest|py\.test|npm|pnpm|yarn|docker|docker-compose|ruff|mypy|tsc|cargo|go|make|generate_types\.sh|alembic|manage\.py)$/) {
        out=$i
        if ($(i+1) ~ /^(compose|run|test|check|format|build|lint|preview|exec)$/) out=out"-"$(i+1)
        if ($(i+2) ~ /^(app|worker|test|lint|build|check|migrate)$/) out=out"-"$(i+2)
        gsub(/[^A-Za-z0-9_.\-]/, "-", out)
        print out
        exit
      }
    }
    print $1
  }
')

SESSION_ID="${CLAUDE_SESSION_ID:-unknown}"
REPO_NAME=$(basename "${CLAUDE_PROJECT_DIR:-$PWD}")
STATE_DIR="$HOME/.claude/state/errors-candidates"
mkdir -p "$STATE_DIR" 2>/dev/null || exit 0
STATE_FILE="$STATE_DIR/${REPO_NAME}-${SESSION_ID}.jsonl"

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SNIPPET=$(printf '%s' "$COMMAND" | head -c 200 | tr '\n' ' ' | jq -Rs .)

printf '{"ts":"%s","kind":"bash","target":"%s","exit_code":%s,"snippet":%s}\n' \
  "$TS" "$TARGET" "$EXIT_CODE" "$SNIPPET" >> "$STATE_FILE"

exit 0
