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
