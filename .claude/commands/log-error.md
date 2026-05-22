---
argument-hint: [promote|review|quick]
description: Log a failed-approach entry to ERRORS.md. Usage — `/log-error` for an interactive entry, `/log-error promote` to review the auto-generated draft, `/log-error quick` for a title-only stub.
effort: low
---

# /log-error

Mode argument: **$ARGUMENTS**

This command edits `ERRORS.md` at the repo root. The schema and policy are defined in `.claude/rules/errors-log.md`. Keep entries terse. Don't paste secrets, prod data, customer names, or full stack traces.

---

## Mode: `promote` (or `review`)

If `$ARGUMENTS` contains `promote` or `review`:

1. Read `${CLAUDE_PROJECT_DIR}/ERRORS.md.draft`.
   - If it doesn't exist or is empty, tell the user: *"No draft available. Use `/log-error` (no args) to make an entry interactively."* and stop.
2. Parse the draft into individual entries split on `## ` headings.
3. For each entry, in order:
   - Show the entry to the user (the title, what didn't work, and the placeholder fields).
   - Use `AskUserQuestion` with options: **Keep as-is**, **Edit before keeping**, **Discard**.
   - If **Edit**: ask the user inline for the corrected `Task type`, `What didn't work`, `What worked`, and `Note for next time`. Reconstruct the entry.
   - If **Keep as-is**: still ask the user to fill in the `<fill in: ...>` placeholders (Task type / What worked / Note) — without those, the entry is low-signal. If the user refuses to fill them, default to discard.
   - If **Discard**: skip.
4. After processing all entries:
   - Read `${CLAUDE_PROJECT_DIR}/ERRORS.md`.
   - Insert the kept entries (newest first, in the order the user kept them) immediately after the `---` separator line that follows the file's header / format block.
   - Write `ERRORS.md` back.
5. Delete `${CLAUDE_PROJECT_DIR}/ERRORS.md.draft` and (best-effort) `~/.claude/state/errors-candidates/<repo>-<session>.jsonl*` so the cluster counter resets.
6. Tell the user: *"Promoted N entries to ERRORS.md. M discarded."*

---

## Mode: `quick` — title-only entry

If `$ARGUMENTS` is exactly `quick` (or `quick` followed by a title):

1. Ask the user (one inline prompt) for a **Title** if not provided in the args.
2. Format the entry as a stub — title + today's date + placeholder body:
   ```
   ## YYYY-MM-DD — <title>
   **Task type:** _(fill in later)_
   **What didn't work:** _(fill in later)_
   **What worked:** _(fill in later)_
   **Note for next time:** _(fill in later)_
   ```
3. Insert into `ERRORS.md` at the top (after the `---` separator).
4. Confirm: *"Stub logged: <title> — fill in via /log-error later."*

Use this when you want to bookmark a failure quickly mid-session; come back to it later with `/log-error` (interactive) to flesh out.

---

## Mode: interactive (no args)

If `$ARGUMENTS` is empty (or anything other than `promote`/`review`/`quick`):

1. Ask the user, one question at a time (use `AskUserQuestion` where the answer is a short choice; inline prompt otherwise):
   - **Title** (short, e.g., `"Pydantic models across Celery worker boundary"`).
   - **Task type** (free text — area / loose category).
   - **What didn't work** (free text — accept multi-line).
   - **What worked** (free text — the approach that landed).
   - **Note for next time** (one line).
2. Format the entry:
   ```
   ## YYYY-MM-DD — <title>
   **Task type:** <task type>
   **What didn't work:** <what didn't work>
   **What worked:** <what worked>
   **Note for next time:** <note>
   ```
   Use today's UTC date (`YYYY-MM-DD`).
3. Read `${CLAUDE_PROJECT_DIR}/ERRORS.md`, insert the new entry immediately after the `---` separator following the file's header / format block, write back.
4. Confirm: *"Logged: <title>"*

---

## Guardrails

- If a similar entry already exists in `ERRORS.md` (match on title or task type), surface it and ask whether to update the existing one instead of creating a duplicate.
- If the situation is already covered by an invariant in `CLAUDE.md` or a rule in `.claude/rules/`, point to that file in the response — don't create a new ERRORS.md entry. The whole point of this log is to capture things that *aren't* yet codified.
- Never log content that looks like a secret (API key shape, JWT shape, password=, etc.) even if the user provides it. Ask for a redacted version.
