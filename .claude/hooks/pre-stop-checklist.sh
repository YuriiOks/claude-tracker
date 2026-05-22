#!/usr/bin/env bash
# Pre-stop reminder checklist — printed before Claude ends the session.
# Covers the most common pre-commit checks for claude-tracker.

echo '✋ Before stopping: did you run npm run lint? if backend touched, did you run make test? did you eyeball both themes? did you grep src/components/ for any data.js keys you renamed?'
