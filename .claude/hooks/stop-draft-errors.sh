#!/usr/bin/env bash
# At session-stop, look at this session's failure candidates. For every
# (target -> count >= 2) cluster, write a draft ERRORS.md entry to
# ${CLAUDE_PROJECT_DIR}/ERRORS.md.draft for the user to review.
#
# Prints a single hint line to stdout, BUT only when the draft content
# actually changes (hash sidecar) — so it stays quiet if Claude stops
# multiple times within one session without new failures.
#
# Reads Stop stdin JSON. Always exits 0.
#
# v2.1.145 background-task awareness:
#   If `background_tasks` contains any running task, the user is just
#   detaching from a background session, NOT ending real work. Skip
#   the draft entirely so we don't spam them with mid-flight noise.
#   If `session_crons` is present, mention it in the draft footer.
#
# v2.1.141-style terminalSequence:
#   On NEW draft (hash changed), send bell + OSC window-title escape
#   directly to /dev/tty so the terminal flashes and the title updates.
#   Using /dev/tty (not v2.1.141's JSON output) keeps the stdout
#   text-feedback contract clean across Claude Code versions.

set -u

# Capture stdin once. Empty-on-fail is fine — script still runs.
INPUT=$(cat 2>/dev/null || echo '')

command -v jq >/dev/null 2>&1 || exit 0

# --- v2.1.145 background-task guard ----------------------------------
# If any background task is still running, suppress the draft entirely.
if [ -n "$INPUT" ]; then
  BG_RUNNING=$(printf '%s' "$INPUT" \
    | jq -r '[.background_tasks // [] | .[] | select(.status == "running")] | length' \
    2>/dev/null || echo 0)
  case "$BG_RUNNING" in
    ""|"0") ;;
    *) exit 0 ;;
  esac

  # session_crons goes into the draft footer if anything's present.
  CRONS=$(printf '%s' "$INPUT" \
    | jq -r '.session_crons // [] | length' \
    2>/dev/null || echo 0)
else
  CRONS=0
fi

SESSION_ID="${CLAUDE_SESSION_ID:-unknown}"
REPO_NAME=$(basename "${CLAUDE_PROJECT_DIR:-$PWD}")
STATE_DIR="$HOME/.claude/state/errors-candidates"
STATE_FILE="$STATE_DIR/${REPO_NAME}-${SESSION_ID}.jsonl"
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
DRAFT_FILE="${REPO_ROOT}/ERRORS.md.draft"
HASH_FILE="${STATE_FILE}.shown_hash"

[ -s "$STATE_FILE" ] || exit 0

CLUSTERS=$(jq -s '
  group_by(.target)
  | map({
      target: .[0].target,
      count: length,
      first_ts: .[0].ts,
      last_ts: (sort_by(.ts) | .[-1].ts),
      exit_codes: (map(.exit_code) | unique),
      snippets: (map(.snippet) | unique)
    })
  | map(select(.count >= 2))
  | sort_by(-.count)
' "$STATE_FILE" 2>/dev/null)

N=$(printf '%s' "$CLUSTERS" | jq 'length' 2>/dev/null)
case "$N" in
  ""|"0") exit 0 ;;
esac

DATE_DAY=$(date -u +%Y-%m-%d)
GEN_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

{
  echo "<!-- ERRORS.md DRAFT — generated $GEN_TS from session ${SESSION_ID} -->"
  echo "<!-- Auto-detected failure clusters this session. Review, edit, then run \`/log-error promote\` to append to ERRORS.md. -->"
  echo ""
  printf '%s' "$CLUSTERS" | jq -r --arg d "$DATE_DAY" '
    .[] |
    "## " + $d + " — `" + .target + "` failed " + (.count|tostring) + "× this session\n" +
    "**Task type:** <fill in: what were you trying to do?>\n" +
    "**What didn'"'"'t work:**\n" +
    (.snippets | map("- `" + (.[0:140]) + "`") | join("\n")) + "\n" +
    "**What worked:** <fill in: the approach that landed>\n" +
    "**Note for next time:** <one line worth remembering>\n"
  '
  if [ "${CRONS:-0}" != "0" ] && [ -n "${CRONS:-}" ]; then
    echo ""
    echo "<!-- Note: ${CRONS} session_cron(s) were active when this draft was generated. -->"
  fi
} > "$DRAFT_FILE" 2>/dev/null

# De-dup the user-facing message: only echo when the draft has changed
if command -v shasum >/dev/null 2>&1; then
  NEW_HASH=$(shasum "$DRAFT_FILE" 2>/dev/null | awk '{print $1}')
else
  NEW_HASH=$(stat -f '%m-%z' "$DRAFT_FILE" 2>/dev/null || echo "$N")
fi
PREV_HASH=""
[ -f "$HASH_FILE" ] && PREV_HASH=$(cat "$HASH_FILE" 2>/dev/null || echo "")

if [ "$NEW_HASH" != "$PREV_HASH" ]; then
  printf '%s' "$NEW_HASH" > "$HASH_FILE"
  # Terminal bell + OSC window-title — only flashes the actual terminal,
  # bypasses Claude's stdio capture entirely. No-op in non-tty envs.
  if [ -w /dev/tty ]; then
    printf '\a\033]0;claude-tracker: errors drafted\007' > /dev/tty 2>/dev/null || true
  fi
  echo "📋 ${N} failure cluster(s) detected. Draft at ERRORS.md.draft — run \`/log-error promote\` to review & commit."
fi

exit 0
