// F16: Single source of truth for the workspace navigation. Used by
// Sidebar (renders nav items) and App.jsx (builds breadcrumbs). Add a route
// here once and both consumers update.
//
// Each entry:
//   id     — route page key (matched against route.page)
//   label  — display label in sidebar + breadcrumbs
//   icon   — icon name from src/icons.jsx
//   crumbs — breadcrumb trail (defaults to ['Workspace', label])
//   badgeKey — name of a dynamic count surfaced via Sidebar prop
//              ('repoCount' → repos.length, 'liveCount' → allLive)
//   accent — optional sidebar styling hint ('live' = green pulse)

export const ROUTES = [
  { id: 'dashboard',   label: 'Dashboard',         icon: 'activity' },
  { id: 'repos',       label: 'Repositories',      icon: 'folder',   badgeKey: 'repoCount' },
  { id: 'live',        label: 'Live Sessions',     icon: 'terminal', badgeKey: 'liveCount', accent: 'live' },
  { id: 'sessions',    label: 'Session Log',       icon: 'clock' },
  { id: 'agents',      label: 'Agents & Skills',   icon: 'bot' },
  { id: 'graph',       label: 'Delegation Graph',  icon: 'git' },
  { id: 'heatmap',     label: 'Activity Heatmap',  icon: 'cpu' },
  { id: 'cost',        label: 'Cost & Tokens',     icon: 'dollar' },
  { id: 'permissions', label: 'Permissions Audit', icon: 'shield' },
  { id: 'plugins',     label: 'Plugins & MCP',     icon: 'plug' },
  { id: 'diff',        label: 'Recent Diffs',      icon: 'diff' },
];

// Lookup helper for breadcrumb building.
export const ROUTE_BY_ID = Object.fromEntries(ROUTES.map(r => [r.id, r]));
