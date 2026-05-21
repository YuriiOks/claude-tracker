# Claude Tracker

Personal dashboard for visualizing Claude Code activity across all my repos. Shows live sessions, repo summaries, agent/skill/command inventories, plugin & MCP usage, permissions audit, cost & tokens, delegation graph, recent diffs.

**Stack**: React 19 + Vite 8 + ESLint flat config. Vanilla CSS (no Tailwind, no styled-components). Fira Code mono + Inter sans. Dark cyan/gold default + light amber/orange theme. No tests yet.

---

## Project intent

The app is a meta-tool: it consumes data **about** my Claude Code usage (sessions, agents fired, skills loaded, MCP tools called, permissions hit) and renders it as a dashboard. Today the data is mocked in `src/data.js`; eventually it should read real sources — JSONL transcripts in `~/.claude/projects/`, plugin caches in `~/.claude/plugins/`, Linear API for ticket linkage, Langfuse for token costs.

Repos to surface (from data.js): jupus, voice, anita-legal, …

---

## Don't break these

1. **Vanilla CSS only** — no preprocessor, no PostCSS plugins beyond what Vite ships. Design tokens live in `src/styles.css` (`:root` and `[data-theme="dark|light"]` blocks).
2. **Fira Code is the primary font** for code, terminal, and most UI; Inter is the secondary sans for prose. Don't introduce a third font without a reason.
3. **Two themes coexist** (`data-theme="dark"` and `data-theme="light"`). Every styled element must work in both. Light mode repurposes `--cyan` → amber, not blue.
4. **Mock data is real to the UI** — `data.js` shape is the contract. If you change a key, update every component that reads it.
5. **Don't introduce TypeScript yet.** This is intentionally JS+JSX while the design solidifies.
6. **Keep `App.jsx` legible.** It's a single-file router right now; defer extraction until ≥3 routes share state.

---

## HTML-first documentation (Thariq pattern)

When generating documentation **for or about this project** — specs, design docs, comparison pages, gotchas pages, runbooks, architecture notes, decision records — **default to standalone HTML** instead of markdown. Markdown stays appropriate for:

- short answers in chat
- README and AGENTS.md (must be markdown)
- code-level docstrings and comments
- simple changelogs

Use HTML when the content has any of: tables (>1 row), diagrams (flow/sequence/state/spatial), code with annotations or callouts, comparisons (A/B/C with pros/cons), config-as-form, design-token panels, charts, embedded images, interactive sliders/toggles. See `skill: html-docs` for templates and patterns. Output to `docs/<slug>.html`. The skill provides 8+ pre-baked templates inspired by [@trq212's HTML-over-Markdown thread](https://x.com/trq212/status/2052809885763747935).

The skill activates automatically when:
- I ask for "a doc/spec/page about X"
- I ask to "compare A vs B" with substance
- I ask to "explain how X works" with diagrams
- I ask for a "design token" / "color palette" / "type scale" panel
- I ask for a config UI (yaml/json with toggles)

Override with explicit "in markdown" if I want plain MD.

---

## Stack details

| Path | Purpose |
|---|---|
| `src/App.jsx` | Single-file app — router, layout, theme/density tweaks, live event stream |
| `src/data.js` | Mocked REPOS, GLOBAL, SESSIONS, LIVE_EVENTS_SEED, LIVE_EVENTS_FUTURE |
| `src/styles.css` | Design tokens + base styles |
| `src/components/` | Sidebar, Topbar, Dashboard, Repos, Sessions, Live, Agents, Pages, Misc, Graph, RepoDetail, AgentDetail, TweaksPanel |
| `project/` | Original design handoff materials (Claude-generated HTML mockup, icons, tweaks panel JSX) |
| `chats/` | Prior design conversations (chat1.md, chat2.md) |
| `docs/` | Generated HTML documentation lives here |
| `public/icons.svg` | SVG sprite |
| `vite.config.js` | Vite config (mostly defaults) |

---

## Common operations

```bash
pnpm install          # or npm install — package.json declares no specific PM
npm run dev           # vite dev server, default port 5173
npm run build         # vite build
npm run lint          # eslint .
npm run preview       # vite preview built app
```

Open generated docs: `open docs/<slug>.html` — they're self-contained, no server needed.

---

## Things to avoid

- Pushing data.js mock changes to production lines without verifying every consumer (Repos, Dashboard, Graph all read it).
- Adding a CSS framework — the existing tokens system is the source of truth.
- Over-engineering routing — the current `useState({page, …})` switch is fine until proven otherwise.
- Generating long markdown when HTML would communicate better (see HTML-first section above).

---

## How to work in this repo

- **Simplicity first.** Minimum code that solves the problem. No abstractions for single-use code. No "flexibility" or "configurability" that wasn't requested. No state-management library, no routing library, no TypeScript yet (see invariant #5). If you wrote 200 lines and it could be 50, rewrite it. Self-test: *"would a senior React+Vite engineer say this is overcomplicated?"* — if yes, simplify.
- **Scope discipline.** Only modify files, functions, and lines directly tied to the current task. No drive-by refactors, no extracting a component while fixing a style, no "I noticed and improved." Spot something worth fixing elsewhere — mention it in one closing line, don't touch it.
- **Flag uncertainty before acting.** Not sure whether a `data.js` change ripples to Graph + Repos + Dashboard, whether a new key needs a default in light theme too, or whether a CSS token already exists with a different name? Say so before writing code.
- **Goal-driven execution.** For any task with more than 2 steps, state success criteria first as something a `npm` command or a visible UI behavior can verify — then outline a plan with explicit checks, and loop until each one passes. Don't accept "make it work"; turn it into "make `<command>` pass" or "make the UI do `<observable thing>` in both themes". Examples:
  - "Add a new dashboard card" → renders in dark + light → `npm run lint && npm run build` clean
  - "Rename a `data.js` key" → grep every consumer first → update all → `npm run dev` and click through Repos / Dashboard / Graph
  - "Refactor a component" → component still mounts → both themes still look right (eyeball + screenshot diff)
  - "Add a route" → keep `useState({page})` switch unless >3 routes share state (invariant #6); verify back/forward works
- **`ERRORS.md`** at the repo root logs approaches that didn't work for this repo (Tailwind rejected, TS-migration premature, light-theme color repurpose, etc.). Read before suggesting fixes for structural changes; append after any approach took more than 2 attempts. Format and rules in `.claude/rules/errors-log.md`. Gitignored.
