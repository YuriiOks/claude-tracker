---
name: implement
argument-hint: [quick] <spec-file-or-ticket-or-description> [--html]
description: Implements a spec while maintaining a running implementation-notes.md (or .html with --html) that captures design decisions, intentional deviations, tradeoffs considered, and open questions for the user. Use when implementing anything non-trivial — feature work, RFC implementation, Linear ticket execution — especially after `/project-onboard` or `/master-plan` produced a spec. Keeps you in the loop on ambiguities the spec didn't cover. Pattern from @trq212 (Thariq).
effort: medium
---

# /implement

**Spec:** $ARGUMENTS

## Mode detection — `quick` vs full

If `$ARGUMENTS` begins with `quick` (whitespace-separated, case-insensitive), strip the keyword from the spec and run in **Quick mode**:

- **Skip the notes file entirely.** No implementation-notes.md is created or updated.
- Open questions still surface, but **inline in the chat reply only** — no scaffolding, no sectioned doc.
- Design-decision entries are not logged. Use sparingly: only for tiny scoped changes that don't deserve a notes file.

Otherwise, run the full mode (default — described below).

---

## Pre-flight (do this first — full mode)

1. **Identify the spec source.** Parse `$ARGUMENTS`:
   - File path (e.g., `docs/projects/acm/PLAN.md`, `specs/feature-x.md`) → read it
   - Linear ticket ID (matches `^[A-Z]+-[0-9]+$`) → fetch via `mcp__claude_ai_Linear__get_issue`
   - Project slug matching an existing `docs/projects/<slug>/PLAN.md` → use that file
   - Otherwise → treat as inline natural-language description

2. **Identify the notes destination:**
   - If the spec is `docs/projects/<slug>/PLAN.md` OR `$ARGUMENTS` is a project slug → `docs/projects/<slug>/implementation-notes.md`
   - Otherwise → `docs/implementation-notes/<feature-slug>.md` (create the dir if needed; derive `<feature-slug>` as kebab-case of the ticket/spec title)

3. **Mode detection:**
   - If the notes file exists → ask: *"continue appending or start fresh?"* (default: continue)
   - Otherwise → fresh

4. **Format:** default markdown; if `--html` flag given, generate HTML using the `kb-style.html` template via `doc-author` (incremental updates) instead.

## Initialize the notes file (fresh mode)

Markdown skeleton:

```markdown
# Implementation notes — <title>

**Spec source:** <link/path to spec>
**Started:** <YYYY-MM-DD HH:MM UTC>
**Status:** in-progress

## Open questions

> Items here block / need user confirmation. Newest first.

_(none yet)_

## Design decisions

> Choices where the spec was ambiguous. Newest first.

_(none yet)_

## Deviations from spec

> Places where the implementation intentionally departs from the spec. Newest first.

_(none yet)_

## Tradeoffs

> Alternatives considered and why the chosen path won. Newest first.

_(none yet)_
```

## During implementation — append entries in real-time

**Append after each non-trivial choice.** Don't batch — the file must always reflect current state so the user can interrupt and steer if needed.

Entry format (each entry under the relevant section, newest first):

```markdown
### YYYY-MM-DD HH:MM — <short title>
**Context:** <what part of the spec / what code you're touching>
**Decision:** <what you chose>
**Why:** <rationale — what made this the right call here>
**Alternatives:** <what else you considered, briefly>
**Files:** <list of files touched for this decision>
```

**What counts as "non-trivial":**
- Spec was silent on an interface contract (e.g., "should this return `None` or raise on miss?")
- Spec said X but the codebase already does Y differently — you picked one
- You're skipping a feature mentioned in spec because of a missing dependency / blocker
- You're changing data shapes the spec didn't specify
- You're picking between 2+ valid library/pattern choices
- You hit a bug in third-party code and worked around it

**What does NOT count (skip these — they're noise):**
- Variable names you chose
- Whitespace / formatting decisions
- Following existing patterns the codebase already establishes
- Trivial type annotations

## Open-question handling

When you can't resolve something without the user:

1. Append an entry to the **Open questions** section at the TOP of the file
2. Pause implementation on the affected code path
3. Mention the open question in the next chat response so the user sees it inline
4. When the user answers, move the resolved entry to **Design decisions** with the answer attributed

## Closing

When you declare implementation complete (tests pass, scope covered):

1. Update `**Status:** complete` + add `**Finished:** <timestamp>`
2. Add a closing summary at the bottom:
   ```markdown
   ## Summary

   - **Files changed:** <count>, paths: <list>
   - **Tests added/passing:** <count> / <result>
   - **Spec coverage:** <complete | partial — see deviations>
   - **Outstanding open questions:** <count, link to section>
   ```
3. If any open questions remain, surface them in the chat reply
4. Print: `Implementation notes: open <absolute-path>`

## Refresh mode (continuing existing file)

If the notes file already exists:

- Don't truncate
- Append new entries with new timestamps
- If `Status: complete` was set previously, change it back to `in-progress`
- Re-run the closing summary at the end

## What this skill does NOT do

- Doesn't replace `/master-plan` — use that to generate the PLAN first; `/implement` consumes it
- Doesn't push commits or open PRs — implementation only
- Doesn't auto-resolve open questions — surfaces them to the user instead
- Doesn't write source code without keeping notes — the notes are non-optional for any change that qualifies as "non-trivial" (full mode)
- `quick` mode is explicitly the exception — use it when the work is too small for notes

## Why this exists

From @trq212: *"as much as you spec there are always still ambiguities and unknown unknowns that come up and this gives the model a good out to make decisions but keep you in the loop."*
