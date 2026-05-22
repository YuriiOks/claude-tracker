# ERRORS.md — repo-local failed-approach log

`ERRORS.md` at the repo root is an append-only log of approaches that didn't work, kept so the same dead end isn't rediscovered next month.

## When to read it
- Before suggesting a fix for any task whose shape matches a logged entry (CSS framework adds, TS migration, theme color repurpose, mock-data refactors, routing extraction, etc.).
- At the start of any session that proposes a structural change.

If an incoming task overlaps a logged failure, surface it: *"This looks like the 2026-04-15 TS-migration entry — invariant #5 still says JSX. Going to add a comment instead."*

## When to append
- After any approach took more than 2 attempts to land.
- After any proposal that hit a hard invariant (vanilla CSS only, JSX only, dual theme, mock contract).
- Not for typos, missing imports, or single-shot fixes.

## Auto-draft pipeline

Two hooks coordinate to produce `ERRORS.md.draft` automatically:

1. **PostToolUse `post:bash:track-failures`** silently records every non-zero `Bash` exit (with a normalized `target` key) into `~/.claude/state/errors-candidates/<repo>-<session>.jsonl`.
2. **Stop `stop:draft-errors`** reads that log at session end. For each `(target → count >= 2)` cluster, it writes a draft entry to `${CLAUDE_PROJECT_DIR}/ERRORS.md.draft` and surfaces a one-line hint. Run `/log-error promote` to review and merge.

### Background-task suppression (v2.1.145)

If the Stop hook stdin shows any `background_tasks` with `status: "running"`, the draft is **skipped entirely**. Rationale: the user is detaching from a background session, not concluding real work — surfacing a "you had failures!" message in that flow would be noise. Once the background task completes and the user returns to it, the next genuine Stop will draft normally.

If `session_crons` is present, a footer note is appended to the draft so future readers know cron-driven sessions were in play.

## Entry format

```
## YYYY-MM-DD — <short title>
**Task type:** <area / loose category>
**What didn't work:** <approaches that failed and why>
**What worked:** <the approach that finally landed>
**Note for next time:** <one line worth remembering>
```

Newest at the top.

## What not to log
- Generic React / Vite advice.
- Anything already covered by a CLAUDE.md invariant — link to it instead.
