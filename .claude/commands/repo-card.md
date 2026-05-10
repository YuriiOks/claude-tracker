---
description: Add a new repo to the dashboard's REPOS array in src/data.js, with sensible defaults and the full shape filled in. Saves the manual cargo-cult of copying an existing entry.
---

# /repo-card — Add a repo to the dashboard

## Usage

`/repo-card <id>` — append a new entry to the `REPOS` array in `src/data.js`.

Optional flags (any can be inferred from the user's filesystem if omitted):
- `--name=<display>` (defaults to `id`)
- `--path=<~/path>` — actual repo path on disk
- `--org=<personal|jupus-legal|...>` (defaults to `personal`)
- `--accent=<hex>` — accent color
- `--language=<stack summary>` — e.g. `"Python · Vue · TS"`
- `--description=<one-line>`

## Examples

```
/repo-card carioca --path=~/Documents/Personal/carioca --org=personal --accent="#788C5D" --language="FastAPI · TS · uv"
/repo-card jupus-staging --path=~/Desktop/jupus-staging --accent="#d97757"
```

## What it does

1. **Activate** `agent: data-shape-keeper`.
2. **Read** `src/data.js` to find the `REPOS` array boundaries.
3. **Read** the actual repo (if `--path` is provided) to derive defaults:
   - Detect git branch via `git branch --show-current`
   - Walk `.claude/agents/`, `.claude/skills/`, `.claude/commands/`, `.claude/rules/` and populate the string arrays
   - Read `.claude/settings.json` for `enabledPlugins` and an MCP servers count if available
4. **Append** a new repo entry with the schema enforced by `skill: data-shape`:
   ```js
   {
     id, name, org, path, description, branch, language, accent,
     isActive: false,                         // user can flip later
     stats: { sessionsToday: 0, sessionsWeek: 0, tokensWeek: 0,
              costWeek: 0, filesEdited: 0, avgSession: "0m" },
     agents: [...],
     skills: [...],
     commands: [...],
     rules: [...],
     plugins: [...],
     mcp: [...],
     permissions: { allow: 0, deny: 0, ask: 0 },
   }
   ```
5. **Verify** by running `npm run lint` (catches typos like extra commas) and listing the new repo in the report.

## Smart defaults

When `--path` points at a real directory, scan to fill in:

| Field | Source |
|---|---|
| `branch` | `git -C <path> branch --show-current` |
| `agents` | `ls <path>/.claude/agents/ \| sed 's/.md$//'` |
| `skills` | `ls <path>/.claude/skills/` |
| `commands` | `ls <path>/.claude/commands/ \| sed 's/.md$//' \| sed 's|^|/|'` |
| `rules` | `ls <path>/.claude/rules/ \| sed 's/.md$//'` |
| `plugins` | parse `.claude/settings.json` `enabledPlugins` keys |
| `permissions` | parse `.claude/settings.json` permissions arrays, count entries |

If `--path` is not set OR the directory has no `.claude/`, leave string arrays empty and let the user fill in manually.

## Constraints

- **NEVER** place the new entry inside `GLOBAL` — it goes in `REPOS`.
- **NEVER** use `tokensWeek: "0"` (string) — must be `0` (integer with optional `_` separators when populated later).
- **PREFER** `isActive: false` initially — let the user flip it from the dashboard.

## Arguments

$ARGUMENTS:
- `<id>` — kebab-case slug
- `--name=<display>` optional
- `--path=<~/path>` optional
- `--org=<...>` optional
- `--accent=<hex>` optional
- `--language=<stack>` optional
- `--description=<line>` optional
