#!/usr/bin/env bash
# Persistent statusLine hook (v2.1.6 + v2.1.97 + v2.1.145).
# Refreshed periodically by Claude Code; stdin is the statusLine JSON
# payload (git info, context window, workspace).
#
# Output: a single line, terse, no newline.
#   Example: "main · PR#42 · ctx 38% · vite running · 2 docs"
#
# Falls back gracefully when jq, git, or fields are missing.

set -u
INPUT=$(cat 2>/dev/null || echo '{}')

PROJECT="${CLAUDE_PROJECT_DIR:-$HOME/Documents/Personal/claude-tracker}"

# --- branch + PR (from stdin JSON, fallback to local git) -------------
BRANCH=""
PR=""
CTX=""
if command -v jq >/dev/null 2>&1; then
  BRANCH=$(printf '%s' "$INPUT" | jq -r '.git.branch // .workspace.git_branch // empty' 2>/dev/null)
  PR=$(printf '%s' "$INPUT" | jq -r '.git.pr.number // empty' 2>/dev/null)
  CTX=$(printf '%s' "$INPUT" | jq -r '.context_window.used_percentage // empty' 2>/dev/null)
fi

# Fallbacks
if [ -z "$BRANCH" ] && [ -d "$PROJECT/.git" ]; then
  BRANCH=$(cd "$PROJECT" && git branch --show-current 2>/dev/null)
fi

# --- local checks (vite + docs) ---------------------------------------
DEV_UP=0
if command -v lsof >/dev/null 2>&1; then
  DEV_UP=$(lsof -ti:5173 2>/dev/null | wc -l | tr -d " ")
fi
DOCS=0
if [ -d "$PROJECT/docs" ]; then
  DOCS=$(ls "$PROJECT"/docs/*.html 2>/dev/null | wc -l | tr -d " ")
fi

# --- assemble ---------------------------------------------------------
PARTS=()
[ -n "$BRANCH" ] && PARTS+=("$BRANCH")
[ -n "$PR" ] && PARTS+=("PR#${PR}")
[ -n "$CTX" ] && PARTS+=("ctx ${CTX}%")
if [ "$DEV_UP" -ge 1 ] 2>/dev/null; then
  PARTS+=("vite running")
else
  PARTS+=("vite stopped")
fi
PARTS+=("${DOCS} docs")

# Join with " · " and print (no newline)
SEP=" · "
OUT=""
for i in "${!PARTS[@]}"; do
  if [ "$i" -eq 0 ]; then
    OUT="${PARTS[$i]}"
  else
    OUT="${OUT}${SEP}${PARTS[$i]}"
  fi
done
printf '%s' "$OUT"
