---
name: dual-theme
description: Use whenever editing CSS, adding styled elements, or reviewing visual changes. Encodes the dark cyan/gold vs light amber/orange theming rules — including the "cyan → amber repurposing" trick that lets one set of CSS rules work in both themes.
origin: claude-tracker
---

# dual-theme — dark cyan ↔ light amber theming

claude-tracker has TWO themes that coexist on every screen. The dark theme is yuriodev cyan/gold cyberpunk; the light theme is warm amber/orange. The trick: instead of writing `if (light) ...` everywhere, the LIGHT theme **repurposes** the `--cyan` semantic role to amber. This way, every rule that uses `var(--cyan)` works in both modes — the value just changes.

## Gotchas (Highest-Signal — Read First)

1. **Light's `--cyan` is amber `#d97706`, NOT blue.** If a designer says "make the active sidebar cyan" — they mean *amber* in light mode. The variable name is semantic, not literal. (See `src/styles.css` `[data-theme="light"]` block.)

2. **Pure blue is reserved for `--teal`** in light mode (used rarely, secondary chart accents only). Don't use `--cyan` for "I want a blue chart line" — use `--teal` (which is cool blue in dark, but ALSO repurposed to deep amber `#c2410c` in light).

3. **`--gold` flips meaning across themes.** Dark: `#FFC107` (vivid amber). Light: `#b45309` (deep amber/brown). Tested in section titles, label chips. Don't introduce gold-specific styling that assumes the dark hue.

4. **`--inv` is the inverse of `--bg`.** Dark: dark navy. Light: white. Used for text-on-accent buttons. Don't hardcode `#fff`.

5. **Glow shadows (`--glow-c`, `--glow-c-strong`) are softer in light.** Dark uses translucent cyan glow; light uses translucent amber. Don't omit the light variant when adding a new glow.

6. **`html[data-theme="dark"] body` and `html[data-theme="light"]` set `background-color !important`.** This is the override that fights any third-party stylesheet bleeding in. Don't remove it.

7. **The Topbar theme toggle writes to `document.documentElement.dataset.theme`.** App.jsx reads `tweaks.theme` and propagates. Don't add a separate theme state.

8. **Light mode flips `h2.section-title` color to `--txt-bright`** (a non-cyan dark text). This is intentional — large amber section titles are too loud in light.

9. **The accent tone tweak (`tweaks.accentTone`) ONLY applies in dark mode.** If you switch the global accent in light, you'll need to add a separate light-tone array.

10. **`<pre>` and `<code>` blocks use `--code-bg` which is dark in dark and a tinted-white in light.** Fira Code reads fine on both. Don't hardcode a code-block background.

## The token system

`src/styles.css` defines tokens twice:

```css
[data-theme="dark"] {
  --bg: #070b14;
  --cyan: #06b6d4;        /* primary accent */
  --gold: #FFC107;
  --teal: #14b8a6;
  /* ... */
}

[data-theme="light"] {
  --bg: #fff7ed;
  --cyan: #d97706;        /* repurposed → amber */
  --gold: #b45309;
  --teal: #c2410c;
  /* ... */
}
```

Components write `color: var(--cyan)` once and it works in both. Magic.

## Adding a new styled element

1. Use existing tokens — `--cyan`, `--gold`, `--teal`, `--purple`, `--green`, `--rose`, `--orange`, `--red`. No raw hex.
2. If you need a *new* role, add it to BOTH `[data-theme="dark"]` and `[data-theme="light"]` blocks of `:root`-style declarations.
3. Test in both: Topbar has the theme toggle. Or in DevTools, edit `<html data-theme="...">` directly.
4. If the element shows differently in the two themes (e.g., a glow on dark only), note it in a CSS comment.

## Adding a new accent tone

Currently dark supports `cyan`, `teal`, `violet`, `rose`, `amber`. App.jsx's effect block reads `tweaks.accentTone` and overrides `--cyan` via `documentElement.style.setProperty`. To add `green`:

1. Pick the hue: `--cyan: #10b981` for example.
2. Add to the `tones` map in `App.jsx` `useEffect`.
3. Add to the `<TweakSelect>` options in `TweaksPanel`.
4. Optional: add a parallel light-mode tone if you also want light to switch.

## Anti-patterns

- ❌ Inline raw hex `#06b6d4` instead of `var(--cyan)`.
- ❌ Adding `[data-theme="dark"]` rules without a `[data-theme="light"]` sibling.
- ❌ Hardcoding white/black for text — use `--txt`, `--txt-bright`, `--inv`.
- ❌ Treating the theme as a binary "dark mode is default" — both are first-class.
- ❌ Forgetting that "cyan" in light mode is amber. Read variable names as roles, not colors.
- ❌ Using `prefers-color-scheme` directly — App.jsx is the source of truth via `data-theme`.

## Quality bar

```bash
# Toggle in browser, eyeball both
npm run dev
# Then in DevTools console:
document.documentElement.dataset.theme = 'light'
document.documentElement.dataset.theme = 'dark'
```

For substantial visual changes, generate a side-by-side comparison via `/doc <feature> --template=design-tokens` so you can verify both themes in one HTML page.
