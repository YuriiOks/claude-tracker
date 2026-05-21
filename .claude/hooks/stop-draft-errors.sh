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

set -u
cat >/dev/null 2>&1 || true

command -v jq >/dev/null 2>&1 || exit 0

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
  echo "📋 ${N} failure cluster(s) detected. Draft at ERRORS.md.draft — run \`/log-error promote\` to review & commit."
fi

exit 0
