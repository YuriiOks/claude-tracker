---
description: Generate a standalone HTML documentation page for a topic, using the html-docs skill templates (Thariq's HTML-over-Markdown pattern). Output goes to docs/<slug>.html.
---

# /doc — Generate an HTML doc

## Usage

`/doc <topic>` — produce `docs/<slug>.html` for the given topic, picking the right template from `skill: html-docs`.

Optional flags (anywhere in the topic):
- `--template=spec|flow|compare|config|tokens|gotchas|code|base` — force a specific template (otherwise the skill picks based on content shape).
- `--md` — fall back to a markdown file at `docs/<slug>.md` instead of HTML (use only when the user explicitly wants markdown).
- `--source=<path-or-url>` — record the synthesis source in the footer.

## Examples

```
/doc how rate limiting works           # → docs/how-rate-limiting-works.html (flow-diagram template)
/doc compare debounce approaches       # → docs/compare-debounce-approaches.html (comparison)
/doc permissions audit spec --template=spec
/doc warm-neutral design tokens        # → docs/warm-neutral-design-tokens.html (design-tokens)
/doc bedrock cache gotchas --template=gotchas
/doc flags.yaml form --template=config
```

## Workflow

1. **Read** any source files referenced (codebase, chats/*.md, recent git diff, web URL via WebFetch).
2. **Pick** the template via the rules in `skill: html-docs`. If unclear, ask the user.
3. **Synthesize** content tightly. Don't pad. Don't include rabbit holes.
4. **Slug** the topic to kebab-case for the filename.
5. **Write** to `docs/<slug>.html`. Inline the contents of `.claude/skills/html-docs/templates/_tokens.css` into the `<style>` block (replace the `@import url("./_tokens.css")` line). Self-contained, no external deps.
6. **Tell the user** the absolute path AND the macOS open command:
   ```
   open /Users/.../claude-tracker/docs/<slug>.html
   ```
7. **Offer one follow-up** — e.g., "want me to add a comparison of approaches at the bottom?" — but don't pile on extras unprompted.

## Constraints

- Don't commit the file unless the user asks.
- One HTML file per call. No chained partials, no `<iframe>` embeds.
- Keep total page weight under 100 KB (no embedded images larger than 64×64 SVG).
- If the topic genuinely needs interactivity beyond a few sliders/toggles, suggest building a React component in `src/components/` instead.

## Arguments

$ARGUMENTS:
- `<topic>` — free-form description of the doc to generate
- `--template=<id>` optional
- `--md` optional
- `--source=<path-or-url>` optional
