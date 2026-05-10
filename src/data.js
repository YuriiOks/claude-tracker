export const REPOS = [
  {
    id: "jupus",
    name: "jupus",
    org: "jupus-legal",
    path: "~/Desktop/jupus",
    description: "Legal tech SaaS — Django + Vue 3 + AI module",
    branch: "feat/ACM-026-bedrock",
    language: "Python · Vue · TS",
    accent: "#d97757",
    isActive: true,
    stats: {
      sessionsToday: 14,
      sessionsWeek: 73,
      tokensWeek: 4_820_000,
      costWeek: 38.42,
      filesEdited: 47,
      avgSession: "8m 42s",
    },
    agents: [
      "jupus-orchestrator",
      "jupus-test-engineer",
      "integration-engineer",
      "jupus-devops",
      "frontend-engineer",
      "ai-developer",
      "backend-engineer",
      "document-specialist",
    ],
    skills: [
      "jupus-type-generation",
      "jupus-provider-adapter",
      "jupus-bedrock-adapter",
      "jupus-action-widget",
      "jupus-acm-testing",
      "jupus-deployment",
    ],
    commands: [
      "/run-tests",
      "/generate-types",
      "/new-event",
      "/acm-status",
      "/start-acm",
      "/deploy-check",
    ],
    rules: [
      "django-conventions",
      "logging-and-errors",
      "acm-architecture",
      "migrations-advanced",
      "bedrock-aws",
      "websocket-consumers",
      "frontend-conventions",
    ],
    plugins: ["linear", "slack", "greptile", "sentry", "pr-review-toolkit", "figma"],
    mcp: ["filesystem", "linear-server", "playwright", "figma", "code-review-graph"],
    permissions: { allow: 142, deny: 4, ask: 8 },
  },
  {
    id: "voice",
    name: "voice",
    org: "jupus-legal",
    path: "~/Desktop/voice",
    description: "Voice bot — Retell + Twilio + WebSocket",
    branch: "main",
    language: "Python · Node",
    accent: "#5a8dee",
    isActive: false,
    stats: {
      sessionsToday: 3,
      sessionsWeek: 19,
      tokensWeek: 980_000,
      costWeek: 7.84,
      filesEdited: 12,
      avgSession: "5m 11s",
    },
    agents: ["voice-engineer", "twilio-specialist", "websocket-debugger"],
    skills: ["retell-prompt-tuning", "twilio-debugging"],
    commands: ["/retell-sync", "/test-call"],
    rules: ["websocket-consumers", "twilio-conventions"],
    plugins: ["linear", "sentry"],
    mcp: ["filesystem", "linear-server"],
    permissions: { allow: 38, deny: 2, ask: 3 },
  },
  {
    id: "anita",
    name: "anita-legal",
    org: "personal",
    path: "~/Desktop/anita",
    description: "Side project — verdict search RAG",
    branch: "exp/embeddings-v3",
    language: "Python · Next.js",
    accent: "#a78bfa",
    isActive: true,
    stats: {
      sessionsToday: 6,
      sessionsWeek: 28,
      tokensWeek: 1_640_000,
      costWeek: 12.91,
      filesEdited: 21,
      avgSession: "11m 03s",
    },
    agents: ["rag-architect", "embeddings-tuner", "next-frontend"],
    skills: ["pgvector-tuning", "verdict-parsing"],
    commands: ["/reindex", "/eval-rag"],
    rules: ["next-app-router", "rag-eval"],
    plugins: ["linear", "greptile"],
    mcp: ["filesystem", "code-review-graph"],
    permissions: { allow: 52, deny: 1, ask: 4 },
  },
  {
    id: "mcp-presentation",
    name: "mcp-servers-presentation",
    org: "personal",
    path: "~/Desktop/jupus/mcp-servers-presentation",
    description: "Conference talk — building MCP servers",
    branch: "main",
    language: "Python · Markdown",
    accent: "#10b981",
    isActive: false,
    stats: {
      sessionsToday: 0,
      sessionsWeek: 4,
      tokensWeek: 210_000,
      costWeek: 1.62,
      filesEdited: 6,
      avgSession: "3m 28s",
    },
    agents: ["slide-writer"],
    skills: ["mcp-server-bootstrap"],
    commands: ["/build-slides"],
    rules: ["talk-conventions"],
    plugins: ["slack"],
    mcp: ["filesystem"],
    permissions: { allow: 21, deny: 1, ask: 2 },
  },
];

export const GLOBAL = {
  id: "global",
  name: "~/.claude (global)",
  path: "~/.claude",
  description: "Global Claude Code setup — applies to every repo",
  agents: ["code-reviewer", "commit-writer", "doc-explorer"],
  skills: ["frontend-design", "code-review", "commit-commands", "pr-review-toolkit"],
  commands: ["/explain", "/refactor", "/changelog"],
  plugins: ["linear", "slack", "sentry", "figma", "pr-review-toolkit", "greptile"],
  mcp: ["filesystem", "sequential-thinking", "linear", "github"],
  permissions: { allow: 78, deny: 4, ask: 6 },
};

export const AGENT_META = {
  "jupus-orchestrator": {
    repo: "jupus",
    role: "Front door — coordinates 7 specialists",
    tools: ["Read", "Glob", "Grep", "Bash", "Task"],
    delegates: [
      "backend-engineer", "frontend-engineer", "ai-developer",
      "document-specialist", "integration-engineer", "jupus-test-engineer", "jupus-devops",
    ],
    callsToday: 8,
    avgTokens: 24_500,
  },
  "jupus-test-engineer": {
    repo: "jupus",
    role: "pytest suite, conftest fixtures, AI benchmarks",
    tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    delegates: [],
    callsToday: 11,
    avgTokens: 18_200,
  },
  "frontend-engineer": {
    repo: "jupus",
    role: "Vue 3, TypeScript, Pinia, Office Add-in",
    tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    delegates: [],
    callsToday: 6,
    avgTokens: 21_400,
  },
  "ai-developer": {
    repo: "jupus",
    role: "AI agents, RAG, document analysis, LLM",
    tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    delegates: [],
    callsToday: 9,
    avgTokens: 32_100,
  },
  "backend-engineer": {
    repo: "jupus",
    role: "Django models, viewsets, migrations, Celery",
    tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    delegates: [],
    callsToday: 12,
    avgTokens: 28_900,
  },
  "integration-engineer": {
    repo: "jupus",
    role: "Actaport, Stripe, Brevo, Cronofy, HubSpot",
    tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    delegates: [],
    callsToday: 2,
    avgTokens: 19_800,
  },
  "jupus-devops": {
    repo: "jupus",
    role: "Docker (14 services), Helm, K8s, Keycloak",
    tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    delegates: [],
    callsToday: 4,
    avgTokens: 14_200,
  },
  "document-specialist": {
    repo: "jupus",
    role: "Word/PDF templates, Jinja2, OnlyOffice",
    tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    delegates: [],
    callsToday: 1,
    avgTokens: 16_700,
  },
};

export const LIVE_EVENTS_SEED = [
  { t: -180, repo: "jupus", kind: "agent_start", agent: "jupus-orchestrator", msg: "Triaging request: 'fix flaky test in test_case_create'" },
  { t: -172, repo: "jupus", kind: "tool", tool: "Read", target: "app/tests/test_cases/test_case_create.py" },
  { t: -168, repo: "jupus", kind: "tool", tool: "Grep", target: "pattern: 'flaky|skip|xfail'" },
  { t: -160, repo: "jupus", kind: "delegate", from: "jupus-orchestrator", to: "jupus-test-engineer", msg: "Investigating fixture race condition" },
  { t: -154, repo: "anita", kind: "agent_start", agent: "rag-architect", msg: "Re-evaluating embeddings on verdict corpus" },
  { t: -150, repo: "jupus", kind: "tool", tool: "Read", target: "app/tests/conftest.py" },
  { t: -141, repo: "jupus", kind: "skill", skill: "jupus-acm-testing", msg: "Loaded testing patterns" },
  { t: -132, repo: "jupus", kind: "tool", tool: "Bash", target: "pytest app/tests/test_cases/test_case_create.py -v" },
  { t: -120, repo: "anita", kind: "tool", tool: "Bash", target: "python eval_rag.py --model claude-haiku" },
  { t: -110, repo: "jupus", kind: "tool", tool: "Edit", target: "app/tests/conftest.py:412" },
  { t: -102, repo: "jupus", kind: "permission", level: "ask", action: "Bash(git commit:*)", granted: true },
  { t: -96, repo: "jupus", kind: "tool", tool: "Bash", target: "git commit -m 'fix: stabilize fixture'" },
  { t: -88, repo: "anita", kind: "tool", tool: "Edit", target: "src/embeddings/processor.py:78" },
  { t: -75, repo: "jupus", kind: "delegate", from: "jupus-test-engineer", to: "jupus-orchestrator", msg: "Fix verified — 50/50 runs pass" },
  { t: -64, repo: "jupus", kind: "agent_start", agent: "ai-developer", msg: "Implementing ACM-026 Bedrock tool conversion" },
  { t: -58, repo: "jupus", kind: "skill", skill: "jupus-bedrock-adapter", msg: "Loaded Bedrock adapter patterns" },
  { t: -52, repo: "jupus", kind: "tool", tool: "Read", target: "app/ai/services/chat/bedrock/tool_conversion.py" },
  { t: -45, repo: "jupus", kind: "tool", tool: "Write", target: "app/ai/services/chat/bedrock/stream_parser.py" },
  { t: -38, repo: "anita", kind: "permission", level: "ask", action: "Bash(docker compose down:*)", granted: false },
  { t: -30, repo: "jupus", kind: "command", cmd: "/generate-types", msg: "Regenerating TS types from schema" },
  { t: -22, repo: "jupus", kind: "tool", tool: "Bash", target: "./generate_types.sh" },
  { t: -14, repo: "jupus", kind: "tool", tool: "Edit", target: "spa-frontend/src/types/generated/types.gen.ts" },
  { t: -6, repo: "jupus", kind: "agent_start", agent: "frontend-engineer", msg: "Building ModelSelector.vue" },
  { t: -2, repo: "jupus", kind: "tool", tool: "Read", target: "spa-frontend/src/components/app/chat/components/" },
];

export const LIVE_EVENTS_FUTURE = [
  { dt: 4, repo: "jupus", kind: "tool", tool: "Write", target: "spa-frontend/src/components/app/chat/components/ModelSelector.vue" },
  { dt: 9, repo: "jupus", kind: "tool", tool: "Edit", target: "spa-frontend/src/composables/useModelSelection.ts" },
  { dt: 14, repo: "anita", kind: "tool", tool: "Bash", target: "pytest tests/test_embeddings.py -v" },
  { dt: 19, repo: "jupus", kind: "skill", skill: "jupus-action-widget", msg: "Loaded widget patterns" },
  { dt: 24, repo: "jupus", kind: "tool", tool: "Read", target: "spa-frontend/src/components/agent-actions/widgets/AgentActionWidget.vue" },
  { dt: 30, repo: "jupus", kind: "permission", level: "ask", action: "Bash(gh pr create:*)", granted: true },
  { dt: 35, repo: "jupus", kind: "tool", tool: "Bash", target: "gh pr create --title 'AI-431 ModelSelector'" },
  { dt: 40, repo: "anita", kind: "delegate", from: "rag-architect", to: "embeddings-tuner", msg: "Retrying with bge-large-en-v1.5" },
  { dt: 46, repo: "jupus", kind: "agent_start", agent: "jupus-test-engineer", msg: "Writing test for ModelSelector" },
  { dt: 52, repo: "jupus", kind: "tool", tool: "Write", target: "spa-frontend/src/__tests__/ModelSelector.spec.ts" },
];

export const SESSIONS = [
  { id: "s1", repo: "jupus", started: "10:42", duration: "12m 04s", agent: "jupus-orchestrator", task: "Fix flaky test in test_case_create", status: "completed", tokens: 142_300, cost: 1.18, edits: 3 },
  { id: "s2", repo: "anita", started: "10:38", duration: "running", agent: "rag-architect", task: "Re-evaluate verdict embeddings", status: "running", tokens: 89_400, cost: 0.71, edits: 1 },
  { id: "s3", repo: "jupus", started: "09:51", duration: "8m 22s", agent: "ai-developer", task: "ACM-026 Bedrock tool conversion", status: "completed", tokens: 218_900, cost: 1.84, edits: 5 },
  { id: "s4", repo: "jupus", started: "09:14", duration: "running", agent: "frontend-engineer", task: "Build ModelSelector.vue", status: "running", tokens: 67_200, cost: 0.54, edits: 2 },
  { id: "s5", repo: "jupus", started: "08:33", duration: "4m 18s", agent: "jupus-devops", task: "Trace docker compose mount issue", status: "completed", tokens: 38_700, cost: 0.31, edits: 0 },
  { id: "s6", repo: "voice", started: "08:01", duration: "5m 11s", agent: "twilio-specialist", task: "Debug ngrok WebSocket disconnect", status: "completed", tokens: 71_400, cost: 0.58, edits: 2 },
  { id: "s7", repo: "anita", started: "yesterday 22:14", duration: "18m 42s", agent: "rag-architect", task: "Tune retrieval k=8 → k=12", status: "completed", tokens: 312_000, cost: 2.49, edits: 4 },
  { id: "s8", repo: "jupus", started: "yesterday 19:22", duration: "22m 16s", agent: "backend-engineer", task: "Migration: add model field to AIChatSession", status: "completed", tokens: 184_100, cost: 1.47, edits: 3 },
  { id: "s9", repo: "jupus", started: "yesterday 16:48", duration: "6m 02s", agent: "document-specialist", task: "Fix Jinja2 hyphen bug in template", status: "completed", tokens: 52_800, cost: 0.42, edits: 1 },
  { id: "s10", repo: "voice", started: "yesterday 14:11", duration: "9m 33s", agent: "voice-engineer", task: "Add Polish language support to Retell", status: "completed", tokens: 96_700, cost: 0.78, edits: 4 },
];

export const PERMISSIONS_DETAIL = {
  allow: [
    "Read(**/.envs/private/**)", "Read(**/.env)", "Read(**/.env.*)", "Read(**/credentials*)", "Read(**/secrets*)",
    "Edit(**/.envs/private/**)", "Edit(**/.env)", "Write(**/.envs/private/**)",
    "Bash(python:*)", "Bash(pytest:*)", "Bash(ruff:*)", "Bash(pnpm:*)", "Bash(npm run:*)", "Bash(npx:*)",
    "Bash(git:*)", "Bash(gh:*)", "Bash(docker compose:*)", "Bash(docker ps:*)", "Bash(docker exec:*)",
    "Bash(./generate_types.sh:*)", "Bash(ls:*)", "Bash(tree:*)", "Bash(curl:*)", "Bash(find:*)",
    "Skill(frontend-design:*)", "Skill(code-review:code-review)", "Skill(pr-review-toolkit:review-pr)",
    "mcp__filesystem__list_directory", "mcp__filesystem__read_text_file", "mcp__linear__get_issue",
    "mcp__linear__list_issues", "mcp__figma__get_design_context", "WebSearch", "WebFetch(domain:claude.com)",
  ],
  deny: [
    "Bash(rm -rf:*)", "Bash(git push --force:*)", "Bash(git reset --hard:*)", "Bash(git clean -f:*)",
  ],
  ask: [
    "Bash(git push:*)", "Bash(git branch -D:*)", "Bash(gh pr create:*)", "Bash(gh pr merge:*)",
    "Bash(gh pr close:*)", "Bash(gh issue create:*)", "Bash(docker-compose down:*)", "Bash(docker compose down:*)",
  ],
};

export const DIFF_SAMPLE = {
  file: "app/ai/services/chat/bedrock/stream_parser.py",
  agent: "ai-developer",
  session: "s3",
  hunks: [
    {
      header: "@@ -42,6 +42,18 @@ class BedrockStreamParser:",
      lines: [
        { type: "ctx", text: "    def parse_event(self, event: dict) -> ChunkEvent | None:" },
        { type: "ctx", text: '        """Translate a Converse stream event into an OpenAI-shaped chunk."""' },
        { type: "ctx", text: "        event_type = event.get('type')" },
        { type: "del", text: "        if event_type == 'contentBlockDelta':" },
        { type: "del", text: "            return ChunkEvent(text=event['delta']['text'])" },
        { type: "add", text: "        if event_type == 'contentBlockStart':" },
        { type: "add", text: "            block = event['contentBlockStart']" },
        { type: "add", text: "            if block.get('toolUse'):" },
        { type: "add", text: "                self._tool_call_accum = ToolCallAccumulator(block['toolUse'])" },
        { type: "add", text: "                return None" },
        { type: "add", text: "" },
        { type: "add", text: "        if event_type == 'contentBlockDelta':" },
        { type: "add", text: "            delta = event['delta']" },
        { type: "add", text: "            if 'toolUse' in delta and self._tool_call_accum:" },
        { type: "add", text: "                self._tool_call_accum.append_input(delta['toolUse']['input'])" },
        { type: "add", text: "                return None" },
        { type: "add", text: "            return ChunkEvent(text=delta.get('text', ''))" },
        { type: "ctx", text: "" },
        { type: "ctx", text: "        if event_type == 'messageStop':" },
        { type: "ctx", text: "            return self._finalize()" },
      ],
    },
  ],
};

export const FILE_SIZES = {
  agents: {
    "jupus-orchestrator": 3914, "jupus-test-engineer": 2904, "integration-engineer": 3655,
    "jupus-devops": 3719, "frontend-engineer": 3871, "ai-developer": 5117,
    "backend-engineer": 4053, "document-specialist": 2898,
    "idor-auditor": 4038, "migration-reversibility": 5320,
    "voice-engineer": 3200, "twilio-specialist": 2800, "websocket-debugger": 2600,
    "rag-architect": 4400, "embeddings-tuner": 3300, "next-frontend": 3100,
    "slide-writer": 2200,
  },
  skills: {
    "jupus-type-generation": 3683, "jupus-provider-adapter": 5531, "jupus-bedrock-adapter": 10871,
    "jupus-action-widget": 4021, "jupus-acm-testing": 8622, "jupus-deployment": 3446,
    "jupus-model-resolution": 7316, "jupus-events": 3778, "jupus-metrics": 3516,
    "jupus-feature-flags": 3216, "jupus-api-design": 5332, "jupus-streaming-service": 6263,
    "jupus-ai-agent-builder": 5496, "langfuse-check": 5890, "find-flag": 5744,
    "add-python-dep": 5039,
    "retell-prompt-tuning": 4100, "twilio-debugging": 3200,
    "pgvector-tuning": 5800, "verdict-parsing": 4900,
    "mcp-server-bootstrap": 3700,
  },
  commands: {
    "/run-tests": 382, "/grill-me": 1167, "/generate-types": 462, "/new-event": 837,
    "/prove-it": 1283, "/acm-status": 1385, "/start-acm": 1737, "/verify-migration": 1615,
    "/deploy-check": 747, "/verify-frontend": 1570,
    "/retell-sync": 920, "/test-call": 1100,
    "/reindex": 880, "/eval-rag": 1240,
    "/build-slides": 760, "/explain": 540, "/refactor": 690, "/changelog": 820,
  },
  rules: {
    "django-conventions": 2526, "logging-and-errors": 1374, "acm-architecture": 4317,
    "migrations-advanced": 2421, "bedrock-aws": 4292, "websocket-consumers": 3238,
    "frontend-conventions": 836,
    "twilio-conventions": 1900,
    "next-app-router": 2100, "rag-eval": 1800,
    "talk-conventions": 1100,
  },
  hooks: {
    "post-tool-use-idor-warn.sh": 779, "post-tool-use-types-nudge.sh": 587,
    "post-tool-use-prettier.sh": 606, "post-tool-use-ruff.sh": 738,
  },
};


// Identity surfaced in the sidebar footer. Backend can later expose /api/user
// reading whoami / git config user.email / Claude account info.
export const USER = {
  name: 'Yurii Oksamytnyi',
  email: 'yurii.oksamytnyi@gmail.com',
  initials: 'YO',
};


// F8: Plugin / MCP descriptions surfaced in PluginsPanel. Backend can later
// expose /api/plugins/registry with the same shape.
export const PLUGIN_REGISTRY = {
  linear: { desc: 'Linear MCP — fetch tickets, projects, comments', accent: 'p' },
  slack: { desc: 'Slack — post updates and read threads', accent: 'g' },
  sentry: { desc: 'Sentry — pull errors and stack traces', accent: 'ro' },
  figma: { desc: 'Figma — extract design context', accent: 'p' },
  greptile: { desc: 'Greptile — codebase semantic search', accent: 't' },
  'pr-review-toolkit': { desc: 'PR Review Toolkit — automated review', accent: 'c' },
};

export const MCP_REGISTRY = {
  filesystem: { desc: 'Local filesystem read/write/search' },
  'sequential-thinking': { desc: 'Multi-step reasoning helper' },
  linear: { desc: 'Linear API server' },
  'linear-server': { desc: 'Linear API (alternate)' },
  github: { desc: 'GitHub API access' },
  playwright: { desc: 'Browser automation' },
  figma: { desc: 'Figma design context' },
  'code-review-graph': { desc: 'Code review graph + impact analysis' },
};

// F11: Claude API pricing — USD per 1M tokens (rough average; refine per model later).
export const MODEL_PRICING_USD_PER_M = {
  default: 8,
  'claude-sonnet-4': 3,
  'claude-opus-4': 15,
};


// F12: Sample agent invocation feed shown on AgentDetail. Backend can later
// surface real per-agent execution log via /api/agents/:name/invocations.
export const AGENT_INVOCATIONS = [
  { t: '2m',  task: 'Audit Bedrock stream parser for empty content blocks', tokens: 4200, status: 'completed' },
  { t: '14m', task: 'Generate TypeScript types from OpenAPI spec',          tokens: 1800, status: 'completed' },
  { t: '38m', task: 'Run ACM-026 test suite end-to-end',                    tokens: 6300, status: 'running'   },
  { t: '1h',  task: 'Investigate stuck SSE in production',                  tokens: 8100, status: 'failed'    },
  { t: '2h',  task: 'Add seed migration for new model descriptions',        tokens: 2200, status: 'completed' },
];


// F13: Recent diff feed shown on DiffPage. Backend can later expose
// /api/diffs/recent-list or similar.
export const RECENT_DIFFS = [
  { t: '2m',  file: 'app/ai/services/chat/bedrock/stream_parser.py',     repo: 'jupus',  a: '+12 −2', agent: 'ai-developer' },
  { t: '8m',  file: 'spa-frontend/src/types/generated/types.gen.ts',     repo: 'jupus',  a: '+47 −3', agent: 'frontend-engineer' },
  { t: '14m', file: 'src/embeddings/processor.py',                       repo: 'anita',  a: '+8 −5',  agent: 'rag-architect' },
  { t: '22m', file: 'app/tests/conftest.py',                             repo: 'jupus',  a: '+3 −1',  agent: 'jupus-test-engineer' },
  { t: '38m', file: 'app/ai/migrations/0058_seed_model_descriptions.py', repo: 'jupus',  a: '+24 −0', agent: 'backend-engineer' },
  { t: '1h',  file: 'retell/handlers/polish_agent.py',                   repo: 'voice',  a: '+18 −4', agent: 'voice-engineer' },
];

export const MOCK_DATA = {
  REPOS, GLOBAL, AGENT_META, LIVE_EVENTS_SEED, LIVE_EVENTS_FUTURE, SESSIONS,
  PERMISSIONS_DETAIL, DIFF_SAMPLE, FILE_SIZES, USER, PLUGIN_REGISTRY, MCP_REGISTRY, MODEL_PRICING_USD_PER_M, AGENT_INVOCATIONS, RECENT_DIFFS,
};
