# Rule: every styled element works in both themes

`data-theme="dark"` and `data-theme="light"` are first-class. Every visual change must be tested in both. The tokens system in `src/styles.css` is built so a single CSS rule using `var(--cyan)` works in both — the value differs.

## Concrete checks before merging a visual change

- [ ] In dev, toggle theme via Topbar (or `document.documentElement.dataset.theme = 'light'` in DevTools).
- [ ] Confirm the element renders correctly in BOTH themes. No invisible text, no white-on-white, no glow that's invisible in light.
- [ ] If a glow / shadow / border looks wrong in one theme, add a theme-specific override in `src/styles.css`.
- [ ] If you introduced a new role/token, add it to BOTH `[data-theme="dark"]` and `[data-theme="light"]` blocks.

## The cyan → amber repurposing trick

In light mode, `--cyan` is `#d97706` (amber), NOT blue. Read variable names as **roles**, not literal colors:

| Role | Dark | Light |
|---|---|---|
| `--cyan` | cyan `#06b6d4` (primary) | amber `#d97706` (primary) |
| `--gold` | vivid amber `#FFC107` | deep amber `#b45309` |
| `--teal` | teal `#14b8a6` (cool secondary) | deep amber `#c2410c` (warm secondary) |
| `--purple` | violet `#a78bfa` | violet `#7c3aed` |
| `--green` | green `#10b981` | green `#059669` |
| `--rose` | pink `#f472b6` | pink `#db2777` |
| `--orange` | amber `#fb923c` | amber `#ea580c` |

Pure cool blue is reserved for charts / rare secondary use — get it via `--teal` in dark mode only, or accept the amber substitute in light.

## Anti-patterns

- ❌ Hardcoding `#06b6d4` instead of `var(--cyan)`.
- ❌ Writing `[data-theme="dark"]` rules without an equivalent for light.
- ❌ Adding `prefers-color-scheme` media queries — the App.jsx-driven `data-theme` attribute is the source of truth.
- ❌ Using `#fff` instead of `var(--inv)` (which flips to dark navy in dark theme).
- ❌ Assuming "cyan" looks blue in both themes. It does not.

## See also

- `skill: dual-theme` — full breakdown including glow shadows, code-block backgrounds, accent-tone tweaks.
- `src/styles.css` — the actual token definitions.
- `App.jsx` — the `useEffect` that reads `tweaks.theme` and `tweaks.accentTone` and propagates.
