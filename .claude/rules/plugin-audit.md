# Rule: Audit every `/plugin` install before accepting

Since Claude Code v2.1.145, `/plugin install` shows a **preview screen** listing every hook, MCP server, skill, LSP entry, and agent the plugin will register. **Read this screen carefully before pressing accept.** Hooks run arbitrary shell on every matched tool call; MCP servers can read your filesystem and call APIs; skills inject text into Claude's context.

## What to check on the preview screen

- [ ] **Hooks** — every hook command runs as you. Inspect each: does the command path look right? Does it touch `~/.ssh`, `~/.aws`, `.env`, or send data over the network?
- [ ] **MCP servers** — what process does it spawn? What env vars does it read? Stdio servers run locally; HTTP servers may reach out to a remote host. Look for `command` + `args` + `env` fields.
- [ ] **Skills** — what `SKILL.md` will be injected? Open the plugin's source if the description hints at writing files, running commands, or accessing credentials.
- [ ] **LSP entries** — language servers run as you and have full read access to your repo. Check the binary path.
- [ ] **Agents** — what `tools:` does each agent get? An agent with `Bash + Write + Edit` can do anything you can do.

If anything looks unexplained or overprivileged → **decline** and inspect the source first.

## Trusted sources

| Source | Trust |
|---|---|
| `claude-plugins-official` (Anthropic) | ✅ high |
| Plugins by people whose code you've already audited | ✅ medium-high |
| Random GitHub plugin you found in a thread | ⚠️ audit source first |
| Plugin recommending itself in a Twitter post | ❌ default-deny |

## Red flags

- Hook commands that `curl | bash` or download/execute remote scripts.
- MCP servers with opaque binaries instead of source-readable scripts.
- Hooks matching `*` (all tools) — almost always overscoped.
- Skills whose description doesn't match what their `scripts/` actually do.
- Plugins requesting `permissions.allow` rules — those should require your explicit consent, not a plugin's.

## After install

- Inspect installed hooks under `~/.claude/plugins/cache/<plugin>/hooks/`.
- Diff against what the preview screen advertised.
- If anything surprises you, `claude plugin remove <name>` immediately.

## See also

- `~/.claude/plugins/installed_plugins.json` — what's actually registered.
- `~/.claude.json` — global MCP server config.
- `CLAUDE.md` "Things to avoid" — points back here.
