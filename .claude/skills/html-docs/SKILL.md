---
name: html-docs
description: Use when generating documentation, specs, lesson decks, grammar concept explainers, comparisons, gotchas pages, runbooks, status reports, prompt-tuning UIs, module maps, design system pages, SVG figures, or interactive editors — produces a self-contained HTML file using the "kb-restructure" design language (warm cream gradient + amber/teal radial accents, glassmorphism cards, Fraunces serif with system fallback, italic+accent emphasis, semantic pill chips, signoff CTAs). 17 templates including the flagship kb-style.html.
origin: carioca · design language modelled on docs/kb-restructure-plan.html
---

# html-docs — generate standalone HTML documentation, not markdown

The default output for substantive documentation in this project is a **single self-contained HTML file**, not markdown. HTML carries 8+ kinds of information markdown cannot: tables (real grid), design tokens, inline SVG diagrams, annotated code, sliders/toggles, workflow boxes-and-arrows, charts and spatial layouts, embedded images, navigable slide decks, collapsible sections, tabbed content, drag-and-drop editors. Same content, structured for **reading and tinkering** instead of scrolling.

This skill encodes that principle plus 17 pre-baked templates inspired by [Thariq's "Unreasonable Effectiveness of HTML"](https://thariqs.github.io/html-effectiveness/) catalog and the **kb-restructure design language** — captured in `_tokens.css` and the flagship `kb-style.html` template, modelled on `docs/kb-restructure-plan.html`.

## ⭐ Flagship: `kb-style.html`

For substantive multi-section docs (specs, restructure plans, audits, decision records, comparison reports), **start with `kb-style.html`** — it has:

- Warm cream gradient background with amber + teal radial accents
- Glassmorphism cards (`backdrop-filter: blur(28px) saturate(180%)`)
- Italic + accent-color emphasis in headings (e.g., `KB <em>restructure</em> plan`)
- Semantic pill system (`.pill.db`, `.pill.md`, `.pill.both`, `.pill.defer`, `.pill.keep`, `.pill.ok`, `.pill.warn`, `.pill.bad`)
- Summary grid with big serif numbers
- KB-style tables (mono cells, accent arrows, sign-off checkboxes)
- Mono-font color-coded directory tree
- Accent-gradient signoff CTA at the bottom
- `<span class="underline-word">` for inline highlights

Fonts: `Fraunces` for display (falls back to system serif), `JetBrains Mono` for code (falls back to system mono), Apple system body. If Fraunces isn't installed locally, the page still renders beautifully on system fonts. **No CDN imports required.**

## When this skill activates

Activate when ANY of these is true:

- User asks for a **spec, design doc, decision record, runbook, RFC, post-mortem, architecture note, gotchas page, comparison, design tokens panel, config UI, status report, lesson deck, grammar concept explainer, prompt-tuning interface, SVG figure, module map**.
- Output would be **>30 lines of markdown** with structure (tables, multiple sections, code blocks, lists with sub-items).
- Content has **at least one** of: tables (>1 row), diagram (flow / sequence / state / spatial / dependency), comparison, code-with-annotation, design tokens, charts, configuration form, embedded screenshot, slide-style content, collapsible details, tabbed code, prompt template with variable slots, drag-and-drop editing.
- User says: "make me a doc" / "explain how X works with diagrams" / "compare A vs B" / "show the design system" / "draft a spec" / "weekly report" / "lesson deck for X" / "explain [grammar concept]" / "tune this prompt".

DO NOT activate when:

- The answer is a single paragraph or under 30 lines.
- User explicitly asks for markdown ("in markdown please", "as a .md file").
- Output is README, AGENTS.md, CLAUDE.md, CHANGELOG, or another file convention requires markdown.
- Output is code-level (docstring, inline comment, JSDoc).

## Output convention

- File path: `docs/<slug>.html` (carioca repo root).
- Filename slug: kebab-case, descriptive. `docs/sm2-algorithm-explainer.html`, not `docs/doc1.html`.
- After writing, tell the user the absolute path AND the macOS open command:
  ```
  open /Users/yurii_jupus/Documents/Personal/carioca/docs/<slug>.html
  ```

## Picking a template

| Pattern | Template | Thariq category | When to use |
|---|---|---|---|
| **Substantive multi-section plan / audit / restructure** | **`kb-style.html` ⭐** | Reports + Editing | **Default flagship.** Header with italic-accent title, summary KPI tiles, glass sections, KB tables with sign-off checkboxes, tree, signoff CTA. Pick this when the doc has ≥3 sections and needs polish. |
| Spec / RFC / decision doc | `spec.html` | Research & Learning | Multi-section spec (Overview · API · Rollout · Risks). Tabs. |
| How something works | `flow-diagram.html` + `annotated-code.html` | Illustrations + Code Review | Explanation with flow at top, code with side notes, gotchas at bottom. |
| Compare approaches | `comparison.html` | Exploration & Planning | A / B / C cards, pros/cons, recommendation highlighted. |
| Config-as-form | `config-form.html` | Custom Editing | YAML/JSON config rendered as toggle list with diff export. |
| Design system | `design-tokens.html` | Design | Color, type, space, button states. |
| Gotchas / pitfalls | `gotchas-callout.html` | Reports | Orange-bar list of pitfalls. Often a section inside a larger doc. |
| PR review | `annotated-code.html` | Code Review | Diff with line-anchored notes (blocking / nit / nice). |
| Module map | `module-map.html` | Code Review | Boxes + arrows for architecture, hot path highlighted. |
| Slide deck | `slide-deck.html` | Decks | Arrow-key navigable slides for lesson decks or talks. |
| Concept explainer | `concept-explainer.html` | Research & Learning | Collapsibles + tabbed forms + glossary. **Best for grammar concepts (subjunctive, prepositions, etc.)** — also Carioca-aware (Amanda anchors, register variations). |
| Feature explainer | `feature-explainer.html` | Research & Learning | Numbered steps + tabbed code (Python/TS/curl) + FAQ. |
| Prompt tuner | `prompt-tuner.html` | Custom Editing | Live-rendered template with variable slots + sliders + copy-as-prompt. **Perfect for tuning AI prompts.** |
| Status report | `status-report.html` | Reports | KPI cards + bar chart + timeline + highlights. **Use for weekly learning summaries.** |
| SVG figure sheet | `svg-figures.html` | Illustrations | Vector diagrams in a grid (flow, ratio, state, stack). |
| Quick reference | `_base.html` + tables | (any) | Use base shell, add tables. |

Inspect templates in `templates/`. Each has structural HTML and inline CSS that uses the shared design tokens from `_tokens.css`.

## Design language (constant across all templates)

The **kb-restructure** design — warm cream gradient with amber/teal radial accents, glassmorphism surfaces, italic+accent typography. These are documentation outputs, **NOT the carioca app's runtime UI** (which uses its own glassmorphism+neumorphism design). Don't conflate the two.

```
/* Background — apply on body */
--bg-app:   linear-gradient(155deg, #F4E3CC 0%, #F7EFE3 60%, #FBFAF7 100%);
--bg-aux1:  radial-gradient(46% 40% at 12% 8%,  rgba(232,159,76,.32), transparent 72%);
--bg-aux2:  radial-gradient(42% 38% at 92% 96%, rgba(30,95,116,.16),  transparent 72%);

/* Text + hairline */
--text-1: #1A1F2E;
--text-2: rgba(26,31,46,.72);
--text-3: rgba(26,31,46,.50);
--hairline: rgba(26,31,46,.10);

/* Glass */
--glass-bg:     rgba(251,250,247,.42);
--glass-border: rgba(255,255,255,.55);
--glass-shadow: 0 18px 50px rgba(120,75,30,.14), inset 0 1px 0 rgba(255,255,255,.65);

/* Accent + semantic palette */
--accent:      #E89F4C;   /* amber primary */
--accent-ink:  #a86b25;   /* darker amber — links, accent text */
--accent-2:    #D45D5D;   /* coral */
--accent-grad: linear-gradient(135deg, #F2C94C 0%, #E89F4C 55%, #D45D5D 110%);
--teal:  #1E5F74;         /* MD / informational */
--plum:  #5C3D7A;         /* keep / preserve */
--green: #3F7D5C;         /* DB / OK */
--coral: #D45D5D;         /* defer / bad */
--gold:  #F2C94C;         /* gold accent */

/* Type */
--font-display: "Fraunces", "Iowan Old Style", "Times New Roman", Georgia, serif;
--font-body:    -apple-system, BlinkMacSystemFont, system-ui, "Segoe UI", Roboto, sans-serif;
--font-mono:    "JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
```

**Italic + accent on emphasis words in headings:** `<h1>KB <em>restructure</em> plan.</h1>` — the `<em>` becomes the amber accent, italic, lighter weight. Use sparingly; one emphasis per heading.

**Underline-word highlight** for inline emphasis in prose: `<span class="underline-word">word</span>` adds a soft amber underline stripe.

## Authoring rules (rigid)

1. **One file, no externals.** Inline CSS and JS. SVG inline. No `<link rel="stylesheet">`, no Google Fonts, no CDN. Self-contained = portable.
2. **Display fonts are system serif.** No Inter import, no Söhne, no Söhne-clone CDN. macOS resolves `ui-serif` to New York; that's the look.
3. **Color sparingly.** Default is text-on-cream. Accent is for ONE thing per page. Multiple accents = noise.
4. **Diagrams are inline SVG.** Not screenshots, not Mermaid (would require build step). Keep markup readable so figures can be tweaked.
5. **Code blocks use `<pre>` with token classes** — each template includes a small JS-free highlight for common languages. Don't pull Prism.
6. **Interactivity is vanilla JS in `<script>` at end of body.** No frameworks. `addEventListener`, `dataset`, `localStorage`. Keep handlers under 60 lines per page.
7. **No JS frameworks** (no React, no Vue, no Alpine, no htmx). The doc is a leaf, not an app.
8. **Accessibility minimums:** semantic landmarks (`<main>`, `<nav>`, `<header>`), heading hierarchy starting at `<h1>`, alt text on `<img>` if any, focus-visible styles preserved, aria-label on icon-only buttons.
9. **Pages should print well.** No fixed positioning that breaks paged media (`slide-deck.html` is the exception — it has explicit `@media print`).
10. **Anchor an "open in browser" line** at the top of every output: a `<small>` with the source date and a "regenerate from" pointer if synthesized from chat/code/web.
11. **For Portuguese/Carioca content**, follow the rules in `skill: portuguese-content` — bilingual side-by-side, Amanda-anchored examples, tutor separation, no subjuntivo without flagging.

## Workflow

When generating a doc:

1. Read the user's request. Identify which template fits (table above).
2. Read source material — codebase files, `~/CC_Setup/*.md`, recent git log, WebFetch for external links.
3. Synthesize tightly. Don't pad. Don't include rabbit holes.
4. Slug the topic to kebab-case.
5. Open the chosen template and copy its content.
6. **Inline the contents of `templates/_tokens.css`** into the `<style>` block — replace the `@import url("./_tokens.css")` line with the actual CSS. Self-contained, no external deps.
7. Replace all `{{PLACEHOLDER}}` markers with real content. Don't leave any `{{...}}` in the output.
8. Write to `docs/<slug>.html`.
9. Tell the user: `open /Users/.../carioca/docs/<slug>.html`.
10. Offer ONE concrete follow-up — e.g., "want a comparison page comparing this to alternative approaches?" — but don't pile on extras unprompted.

## What NOT to put in a doc

- Rabbit holes ("here are 14 alternatives I considered"). Pick one. Note alternatives in a single line.
- Long quotes from the codebase. Excerpt the part that matters; link the file path.
- Decorative animations. Subtle hover/focus is fine; nothing more.
- Logos / branding. This is documentation, not marketing.
- Anything you wouldn't read on a 13" laptop screen at 100% zoom.
- Filler sections ("Background" / "Context" / "Conclusion") if they're not earning their keep.

## Quick-start usage examples

| User says | Template + slug |
|---|---|
| "draft a spec for the audio upload feature" | `spec.html` → `docs/audio-upload-spec.html` |
| "explain how SM-2 works" | `feature-explainer.html` → `docs/sm2-algorithm-explainer.html` |
| "compare three approaches to vocab review queue ordering" | `comparison.html` → `docs/vocab-queue-ordering-comparison.html` |
| "deck for tomorrow's Patricia lesson on imperfeito vs perfeito" | `slide-deck.html` → `docs/imperfeito-vs-perfeito-deck.html` |
| "explain the subjuntivo when I'm ready" | `concept-explainer.html` → `docs/subjuntivo-concept.html` |
| "tune the lesson transcription prompt" | `prompt-tuner.html` → `docs/lesson-transcription-prompt-tuner.html` |
| "weekly status — what did I cover this week" | `status-report.html` → `docs/weekly-status-{{date}}.html` |
| "draw the backend module map" | `module-map.html` → `docs/backend-module-map.html` |
| "design tokens used in the app UI" | `design-tokens.html` → `docs/runtime-design-tokens.html` |
| "annotate the diff for PR #X" | `annotated-code.html` → `docs/pr-{{N}}-review.html` |

## Keeping markdown when appropriate

Don't fight the format. Keep markdown for:

- One-paragraph answers
- README (must stay markdown for GitHub rendering)
- AGENTS.md (must stay markdown — multi-tool spec)
- CLAUDE.md (Claude Code reads it as markdown context)
- CHANGELOG (markdown convention)
- Inline code comments and docstrings
- Carioca knowledge base files in `~/CC_Setup/` (the markdown shape there is intentional and must be preserved)

If unclear: ask the user "want this as HTML or stay in markdown?" before generating.
