# Rule: src/data.js shape is the contract

`src/data.js` is read by 12+ component files. It's mocked but it's the contract — every panel's render depends on a stable shape. Treat changes to it like a public API change.

## Hard rules

1. **Grep before renaming any key.** `grep -rn "<keyname>" src/components/` will surface every consumer. Update them in the same change. Never ship a `data.js` rename and consumer updates in separate commits — they have to land together.
2. **Additive changes are safe.** Adding a new optional key is preferred over renaming an existing one.
3. **Don't add network I/O to `data.js`.** It must stay pure mock. For real data sources, use the migration path in `skill: data-shape` — add `src/dataSources/` alongside.
4. **Don't mutate items in `REPOS` from components.** React won't re-render. If you need to edit a repo's stats, route through state, not the imported array.
5. **Preserve numeric separators (`4_820_000`)** in code. Don't `JSON.stringify` and re-parse — the underscores get dropped.
6. **`GLOBAL` is `id: 'global'`.** Components that filter "real repos only" must check `id !== 'global'`.

## Cross-references

- `skill: data-shape` — the four shapes documented with field-by-field semantics, gotchas, lookup tables.
- `agent: data-shape-keeper` — the specialist for shape changes. Delegate via `tracker-orchestrator`.
- `command: /repo-card` — interactive scaffolder for adding repos.
- `App.jsx` — the `allRepos = [...repos, GLOBAL]` and `useLiveStream` hook are the chief consumers.

## Quality gate

After any shape change:

```bash
grep -rn "<changed-key>" src/    # find consumers
npm run lint                     # catches dead refs
npm run dev                      # eyeball every affected screen
```
