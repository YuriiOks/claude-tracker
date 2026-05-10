# Rule: Vanilla CSS only — no frameworks

claude-tracker uses **`src/styles.css` as the single source of styling truth**. Design tokens via `:root` + `[data-theme="..."]`. No framework, no preprocessor, no CSS-in-JS, no PostCSS plugins beyond what Vite ships out of the box.

## What's allowed

- Vanilla CSS files imported from `src/styles.css` (or co-located CSS modules if needed — but currently one big file is fine for the size).
- Design tokens (`var(--cyan)`, `var(--bg)`, etc.) defined in the two `[data-theme]` blocks.
- `:root` for global font + spacing scales.
- Vite's built-in CSS handling (auto-prefixing, hashed asset URLs).
- Inline `style={{ color: repo.accent }}` for *data-driven* one-off colors (the repo `accent` field is the canonical use case).

## What's NOT allowed

- ❌ Tailwind, UnoCSS, WindiCSS, etc.
- ❌ styled-components, emotion, vanilla-extract, stitches.
- ❌ SASS, LESS, Stylus, PostCSS-with-plugins.
- ❌ CSS-in-JS template strings.
- ❌ Inline styles for static values (`style={{ color: '#06b6d4' }}` — use a token instead).

## Why

- The mock-dashboard nature means the CSS is small (~700 lines) and can stay in one file.
- The dual-theme trick (cyan ↔ amber repurposing) only works cleanly with vanilla tokens — frameworks fight it.
- Fewer dependencies → fewer security advisories → faster `npm install`.

## Adding a new style

1. Use an existing token. Check `[data-theme="dark"]` and `[data-theme="light"]` blocks for the role you need.
2. If the role doesn't exist, add it to BOTH blocks at the same time. Don't ship dark-only or light-only tokens.
3. Reference via `var(--name)` in your component class.
4. Eyeball both themes via the Topbar toggle.

See also: `skill: dual-theme` for the cyan → amber repurposing trick.
