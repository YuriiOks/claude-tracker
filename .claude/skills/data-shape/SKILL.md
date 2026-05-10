---
name: data-shape
description: Use when reading, modifying, or extending src/data.js — the contract every dashboard component depends on. Encodes the four mock shapes (REPOS, GLOBAL, SESSIONS, LIVE_EVENTS_*) and the migration strategy from mocked-to-real data sources.
origin: claude-tracker
---

# data-shape — the src/data.js contract

`src/data.js` is the single source of mock truth. Every dashboard panel reads from it. Treating it as a contract (not a sketch) keeps the UI from regressing every time a key gets renamed.

## Gotchas (Highest-Signal — Read First)

1. **`accent` is BOTH a hex string in `data.js` AND a CSS-variable lookup in `tokens.css`.** Components do `style={{ color: repo.accent }}` inline. Renaming this field to `color`/`hue`/`brand` causes silent visual breakage in ~5 panels.

2. **`permissions` is `{allow: number, deny: number, ask: number}` — not arrays of rules.** The PermissionsPanel renders the *counts*, not the rule list itself. Don't switch to arrays without rewriting that panel.

3. **`isActive` drives the live-indicator dot AND the `allLive` count in App.jsx Topbar.** Setting all repos to `false` removes the live count entirely.

4. **`stats.tokensWeek` uses ES2021 numeric separators (`4_820_000`).** Don't accidentally `JSON.stringify` and reload — JSON drops the underscores. Either keep them in code OR switch to bare integers.

5. **`LIVE_EVENTS_FUTURE` items have a `dt` field that gets *added to* the previous timestamp** in App.jsx's `useLiveStream`:
   ```js
   t: prev[prev.length - 1].t + (e.dt || 3)
   ```
   So `dt` is "seconds-since-last-event", not absolute. New event shapes must include `dt` or the timestamps drift.

6. **`useLiveStream` keeps a sliding window of 60 events** (`next.slice(-60)`). Pushing 1000 future events doesn't speed it up — they cycle.

7. **`GLOBAL` is merged into `allRepos` in App.jsx via `[...repos, GLOBAL]`.** Components that filter "real repos only" need to check `id !== 'global'`. Forgetting this leaks the workspace aggregate into per-repo charts.

8. **AgentDetail looks up agents by string name match.** If we add structured metadata (turning `agents: string[]` → `agents: AgentRef[]`), keep a name-string fallback or rewrite the lookup.

9. **Numbers in `stats.*` are sometimes formatted (`8m 42s` for `avgSession`) and sometimes raw (`4_820_000` for `tokensWeek`).** `avgSession` is a string. Don't try to math-add.

## The four shapes

```ts
type Repo = {
  id: string;
  name: string;
  org: string;
  path: string;             // ~/Desktop/jupus, ~/Documents/Personal/anita, etc. — or null for GLOBAL
  description: string;
  branch: string;
  language: string;          // "Python · Vue · TS"
  accent: string;            // hex color "#d97757"
  isActive: boolean;
  stats: {
    sessionsToday: number;
    sessionsWeek: number;
    tokensWeek: number;       // raw int with underscores
    costWeek: number;         // float, USD
    filesEdited: number;
    avgSession: string;       // pre-formatted "8m 42s"
  };
  agents: string[];           // ["jupus-orchestrator", ...]
  skills: string[];           // ["jupus-bedrock-adapter", ...]
  commands: string[];         // ["/run-tests", "/generate-types", ...]
  rules: string[];            // ["django-conventions", ...]
  plugins: string[];          // ["linear", "slack", ...]
  mcp: string[];              // ["filesystem", "linear-server", ...]
  permissions: { allow: number; deny: number; ask: number };
};

type Session = {
  id: string;
  repoId: string;             // FK to Repo.id (or 'global')
  started: string | number;   // ISO or Unix
  duration: number;           // seconds
  tokens: number;
  cost: number;
  agentsUsed: string[];
  filesEdited: number;
};

type LiveEvent = {
  t: number;                  // SEED uses seconds-since-stream-start
  kind: 'tool_use' | 'agent_invoke' | 'edit' | 'commit' | 'permission';
  repoId: string;
  label: string;
  dt?: number;                // FUTURE only: seconds-since-last-event (default 3)
};
```

## Adding a new repo

Use `/repo-card <id>` for the interactive scaffolder. Or by hand:

```js
{
  id: "<slug>",
  name: "<display>",
  org: "<personal | jupus-legal | ...>",
  path: "~/<...>",
  description: "<one-line>",
  branch: "<active-branch>",
  language: "<Stack · summary>",
  accent: "<hex>",
  isActive: <bool>,
  stats: {
    sessionsToday: 0, sessionsWeek: 0, tokensWeek: 0,
    costWeek: 0, filesEdited: 0, avgSession: "0m",
  },
  agents: [], skills: [], commands: [], rules: [],
  plugins: [], mcp: [],
  permissions: { allow: 0, deny: 0, ask: 0 },
}
```

Sidebar will show it automatically (App.jsx maps over `repos`).

## Migration: mocked → real (future)

When you wire real data, do NOT replace `data.js` directly. Add `src/dataSources/`:

```
src/dataSources/
├── jsonlTranscripts.ts    # ~/.claude/projects/<hash>/<sessionId>.jsonl
├── pluginCache.ts         # ~/.claude/plugins/cache/<marketplace>/<plugin>/
├── linear.ts              # Linear API (token in env)
└── langfuse.ts            # Langfuse API
```

Each source returns the same shapes above — the dashboard panels never know they're real vs mocked. `data.js` stays as the design-time fallback.

This is a substantial refactor — produce `/doc compare three approaches to data-source migration` first; pick one with `comparison.html`.

## Anti-patterns

- ❌ Inlining literal hex colors in components instead of `repo.accent`.
- ❌ Mutating items in `REPOS` from inside components (`repo.isActive = true`). React won't notice.
- ❌ Adding network I/O to `data.js` itself (it must stay pure mock).
- ❌ Renaming keys without `grep -rn '<key>' src/components/`.
- ❌ Removing `GLOBAL` filter checks (`id !== 'global'`) in per-repo charts.
- ❌ Treating `stats.avgSession` as a number — it's a pre-formatted string.

## Lookup commands

```bash
grep -rn "repo\." src/components/ | head    # all field accesses
grep -rn "REPOS\b\|GLOBAL\b\|SESSIONS\b\|LIVE_EVENTS_" src/   # all imports
grep -n "useLiveStream" src/App.jsx          # the live-events handler
```
