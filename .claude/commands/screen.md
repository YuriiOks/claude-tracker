---
description: Scaffold a new dashboard screen — create the component, wire the route, add to Sidebar, register crumbs, and remind to test both themes.
---

# /screen — Add a new screen

## Usage

`/screen <name>` — scaffold a new screen `src/components/<Name>.jsx`, wire it into App.jsx as a route, add a Sidebar nav entry, and register crumbs.

Optional flags:
- `--lazy` — wrap in `React.lazy(() => import(...))` (recommended for screens >300 LOC).
- `--icon=<svg-id>` — sidebar icon id from `public/icons.svg`. Defaults to `grid3`.
- `--placeholder` — leave the body as a single empty-state div (skip data wiring).

## Examples

```
/screen Notebooks
/screen LangfuseTraces --lazy --icon=database
/screen Errors --placeholder
```

## What it does

1. **Activate** `agent: react-engineer`.
2. **Read** `src/App.jsx` to understand the current router shape (`route.page` switch + `crumbs` map).
3. **Read** `src/components/Sidebar.jsx` to understand the nav-item pattern.
4. **Read** `src/data.js` to determine which existing shape feeds this screen (`REPOS`? `SESSIONS`? new shape?).
5. **Generate** `src/components/<Name>.jsx`:
   - Functional component
   - Default export OR named `<Name>Page` matching neighbors
   - Receives data via props (no global imports beyond `data.js` shapes)
   - Uses `<PageHead title sub actions={...}>` for header
6. **Edit** `src/App.jsx`:
   - Add route case to `renderPage()` switch
   - Add to `crumbs` map: `<name>: ['Workspace', 'Display Name']`
   - Lazy-import if `--lazy`
7. **Edit** `src/components/Sidebar.jsx`:
   - Add nav button with the requested icon
8. **Verify**:
   - `npm run lint` clean
   - `npm run dev` opens; the new screen renders empty-state without crashing
   - Both themes render

## Constraints

- **NEVER** put screen-specific styles in component files. Add to `src/styles.css` if reusable, otherwise scoped class in same file but using design tokens.
- **NEVER** introduce a new top-level data shape silently. If the screen needs new data, delegate to `data-shape-keeper` first.
- **NEVER** skip the crumbs map — page tabs without crumbs look broken in the Topbar.
- **PREFER** `--lazy` for screens that pull in chart libs, large component trees, or heavy assets.

## Output

Report:
- Files created/modified
- Lint status
- Open command: `npm run dev` then navigate to the new sidebar item

## Arguments

$ARGUMENTS:
- `<name>` — screen name in PascalCase
- `--lazy` optional
- `--icon=<id>` optional
- `--placeholder` optional
