---
description: Run the Jupus test suite with optional filtering
---

Run the Jupus pytest suite: $ARGUMENTS

Steps:
1. If arguments provided, use as filter: `pytest app/tests/ -v -k "$ARGUMENTS"`
2. If no arguments, run full suite: `pytest app/tests/ -v`
3. If tests fail, show the failure summary with file paths and line numbers
4. Report: total tests, passed, failed, duration
