#!/usr/bin/env bash
# Session-start banner: prints branch + dev-server status + recent docs count.
# Output appears in Claude's session header at startup.

set -u

cd "${CLAUDE_PROJECT_DIR:-$HOME/Documents/Personal/claude-tracker}" 2>/dev/null || exit 0

BRANCH=$(git branch --show-current 2>/dev/null)
DEV_UP=$(lsof -ti:5173 2>/dev/null | wc -l | tr -d " ")
DOCS=$(ls docs/*.html 2>/dev/null | wc -l | tr -d " ")

echo "📊 claude-tracker | branch: $BRANCH | vite: $([ "$DEV_UP" -ge 1 ] && echo running || echo stopped) | $DOCS doc(s) in docs/"
