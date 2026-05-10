---
name: html-docs
description: Use when generating documentation, specs, design notes, comparisons, gotchas pages, runbooks, or architecture docs that benefit from structure beyond linear prose — produces a self-contained HTML file using Thariq's HTML-over-Markdown pattern (warm-neutral palette, serif display, inline SVG, optional vanilla-JS interactivity).
origin: claude-tracker
---

# html-docs — generate standalone HTML documentation, not markdown

The default output for substantive documentation in this project is a **single self-contained HTML file**, not a markdown file. HTML carries 8 kinds of information markdown cannot: tables (real grid), design tokens, inline SVG diagrams, annotated code, sliders/toggles, workflow boxes-and-arrows, charts and spatial layouts, embedded images. Same content, structured for **reading** instead of scrolling.

This skill encodes that principle plus pre-baked templates so you don't reinvent the design language each time.

## When this skill activates

Activate when ANY of these is true:

- User asks for a **spec, design doc, decision record, runbook, RFC, post-mortem, architecture note, gotchas page, comparison, design tokens panel, config UI**.
- Output would be **>30 lines of markdown** with structure (tables, multiple sections, code blocks, lists with sub-items).
- Content has **at least one** of: tables (>1 row), diagram (flow / sequence / state / spatial), comparison of approaches, code-with-annotation, design tokens, charts, configuration form, embedded screenshot/figure.
- User says "make me a doc" / "explain how X works with diagrams" / "compare A vs B" / "show me the design system" / "draft a spec".

DO NOT activate when:

- The answer is a single paragraph or under 30 lines.
- User explicitly asks for markdown ("in markdown please", "as a .md file").
- The output is README, AGENTS.md, CLAUDE.md, CHANGELOG, or another file convention requires markdown.
- Output is code-level (docstring, inline comment, JSDoc).

## Output convention

- File path: `docs/<slug>.html` (project root). Create the file with the Write tool. Don't commit unless asked.
- Filename slug: kebab-case, descriptive. `docs/how-rate-limiting-works.html`, not `docs/doc1.html`.
- After writing, tell the user the absolute path AND the macOS open command:
  ```
  open /Users/.../docs/how-rate-limiting-works.html
  ```

## Picking a template

Each template is a starting point. Compose freely, but keep one HTML file per doc.

| Pattern | Template | When to use |
|---|---|---|
| Spec / RFC / decision doc | `spec.html` | Multi-section spec (Overview, API, Rollout). Tabs for navigation. |
| How something works | `flow-diagram.html` + `annotated-code.html` | Synthesized explanation with a flow at the top, code with side notes, gotchas bottom. |
| Compare approaches | `comparison.html` | A / B / C cards, pros/cons, recommendation highlighted. |
| Config-as-form | `config-form.html` | YAML/JSON config rendered as toggle list with diff export. |
| Design system | `design-tokens.html` | Color, type, space, button states. |
| Gotchas / pitfalls | `gotchas-callout.html` | Orange-bar list of pitfalls. Often a section inside a larger doc. |
| Quick reference / cheat sheet | `_base.html` + tables | Use base shell, add tables. |

Inspect templates in `templates/`. Each has structural HTML you can edit and inline CSS that uses the shared design tokens from `_tokens.css`.

## Design language (constant across templates)

These are the tokens. Every template references them. Don't drift.

```
/* Color */
--bg:        #FAF8F5   /* page */
--surface:   #F0EDE8   /* cards, code-mute */
--border:    #D4CFC7
--text:      #2C2825   /* body */
--muted:     #8A837A
--accent:    #B8602A   /* clay — primary action / "selected" / blocking */
--clay:      #D97757   /* warmer accent — buttons, primary highlights */
--olive:     #788C5D   /* secondary accent — "passing"/"good" */
--sky:       #6A8CAF   /* tertiary accent — info */
--oat:       #E3DACC   /* surface 2 — used inside cards */
--slate:     #141413   /* near-black — code background, dark callouts */
--ok:        #5C8C5A   /* additions / success */
--warn:      #C46A3D   /* nits / warnings */
--bad:       #B14D45   /* deletions / errors */

/* Type — system fonts, no CDN */
--font-display: ui-serif, Georgia, "Iowan Old Style", "Apple Garamond", serif;
--font-body:    system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
--font-mono:    ui-monospace, Menlo, Consolas, "SF Mono", monospace;

/* Type scale */
--text-display: 32px / 1.15 var(--font-display);
--text-heading: 20px / 1.3  var(--font-display);
--text-body:    15px / 1.55 var(--font-body);
--text-small:   13px / 1.45 var(--font-body);
--text-mono:    13px / 1.55 var(--font-mono);

/* Space */
--s-1: 4px;  --s-2: 8px;   --s-3: 12px;  --s-4: 16px;
--s-5: 24px; --s-6: 32px;  --s-7: 48px;  --s-8: 64px;

/* Radius */
--radius-1: 4px;  --radius-2: 8px;  --radius-3: 12px;
```

## Authoring rules

1. **One file, no externals.** Inline CSS and JS. SVG inline. No `<link rel="stylesheet">`, no Google Fonts, no CDN. Self-contained = portable.
2. **Display fonts are system serif.** No Inter import, no Söhne. macOS resolves `ui-serif` to New York or similar; that's the look.
3. **Color sparingly.** Default is text-on-cream. Accent is for ONE thing per page (the selected tab, the recommended option, the important callout). Multiple accents = noise.
4. **Diagrams are inline SVG.** Not screenshots, not Mermaid (would require a build step). Keep the markup readable so diagrams can be tweaked.
5. **Code blocks use `<pre>` with token classes** — each template includes a small JS-free highlight for common languages (keywords, strings, comments). Don't pull Prism.
6. **Interactivity is vanilla JS in `<script>` at end of body.** Sliders/toggles work without a framework. Use `addEventListener`, `dataset`, `localStorage`. Keep handlers under 40 lines total per page.
7. **No JS frameworks** (no React, no Vue, no Alpine). The doc is a leaf, not an app. If interactivity grows beyond a few sliders, reconsider whether it should be a React component in the actual app instead.
8. **Accessibility minimums:** semantic landmarks (`<main>`, `<nav>`, `<header>`), heading hierarchy starting at `<h1>`, alt text on `<img>` if any, focus-visible styles preserved, aria-label on icon-only buttons.
9. **Pages should print well.** No fixed positioning that breaks paged media. Test with `Cmd+P → Save as PDF` mentally.
10. **Anchor an "open in browser" line** at the top of every output: a `<small>` with the source date and a "regenerate from" pointer if synthesized from chat/code/web.

## What NOT to put in a doc

- Rabbit holes ("here are 14 alternatives I considered"). Pick one. Note alternatives in a single line.
- Long quotes from the codebase. Excerpt the part that matters; link the file path.
- Decorative animations. Subtle hover/focus is fine; nothing more.
- Logos / branding. This is documentation, not marketing.
- Anything you wouldn't read on a 13" laptop screen at 100% zoom. Test viewport.

## Quick-start usage

The user typed: *"draft a spec for the new permissions audit page"*

1. Pick template: `spec.html`.
2. Slug: `permissions-audit-spec`.
3. Write to `docs/permissions-audit-spec.html`.
4. Tell the user: `open /Users/yurii_jupus/Documents/Personal/claude-tracker/docs/permissions-audit-spec.html`.
5. Offer to extend: "want me to add a flow diagram for the audit pipeline, or a comparison of severity-bucketing approaches?"

The user typed: *"compare three options for how we should fetch live events"*

1. Pick template: `comparison.html`.
2. Slug: `live-events-fetch-comparison`.
3. Three cards (polling / SSE / WebSocket), pros/cons, recommendation highlighted.
4. Open command + offer follow-ups.

## Keeping markdown when appropriate

Don't fight the format. Keep markdown for:

- One-paragraph answers
- README (which must stay markdown for GitHub rendering)
- AGENTS.md (must stay markdown — multi-tool spec)
- CLAUDE.md (Claude Code reads it as markdown context)
- CHANGELOG (markdown convention)
- Inline code comments and docstrings

If unclear: ask the user "want this as HTML or stay in markdown?" before generating.
