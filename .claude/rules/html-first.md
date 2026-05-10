# Rule: HTML-first for substantive documentation

When generating documentation **for or about this project**, default to a self-contained `.html` file at `docs/<slug>.html` rather than a markdown file. This is the Thariq pattern — same content, structured for **reading** instead of scrolling.

## Use HTML when

- Output would be **>30 lines** of markdown with structure.
- Content has any of:
  - Tables (>1 row)
  - Diagrams (flow, sequence, state, spatial)
  - Code with annotations / side notes / callouts
  - Comparisons of approaches with pros/cons
  - Design tokens (colors, type, spacing, components)
  - Configuration as form (YAML/JSON with toggles)
  - Charts or spatial layouts
  - Embedded images or screenshots
  - Sliders, toggles, or any interactivity
- User asks for: spec, RFC, design doc, decision record, runbook, post-mortem, architecture note, gotchas page, comparison, design system page.

## Use markdown when

- Answer is a single paragraph or one short list.
- Output is README, AGENTS.md, CLAUDE.md, CHANGELOG (file convention requires markdown).
- Output is code-level: docstring, JSDoc, inline comment.
- User explicitly says "in markdown" or "as a .md file".

## How

Use the `html-docs` skill — it provides templates (`spec`, `flow-diagram`, `comparison`, `config-form`, `design-tokens`, `gotchas-callout`, `annotated-code`, `_base`) and design tokens (`_tokens.css`).

Use the `/doc <topic>` slash command to invoke the workflow with a single line.

The `doc-author` agent is the specialist; it activates proactively when documentation is requested.

## Quality bar

- One self-contained file, no CDN.
- System fonts only (`ui-serif`, `system-ui`, `ui-monospace`).
- One accent per page — not multiple.
- Prints to one or two pages cleanly.
- No filler sections.

## Reference

Inspired by [@trq212's HTML-over-Markdown thread](https://x.com/trq212/status/2052809885763747935) — see screenshots in `chats/` if archived.
