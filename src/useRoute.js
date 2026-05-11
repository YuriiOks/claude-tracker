// HTML5 History API router. Replaces useState({page:'dashboard'}) so each
// page/repo/agent gets a unique URL, browser back/forward work, and deep
// links survive refresh.
import { useState, useEffect, useCallback } from 'react';

// URL → route state. Inverse of buildPath.
//
// Supported:
//   /                              → dashboard
//   /<page>                        → top-level page (repos, agents, live, ...)
//   /repos/:repoId                 → repo detail (default tab=overview)
//   /repos/:repoId/:tab            → repo detail with active tab (agents, skills, commands, rules, permissions, plugins)
//   /repos/:repoId/:tab/:name      → drill into an item inside the repo
//   /agents/:name                  → global agent detail
//   /agents/:name/:kind            → global agent/skill detail (kind explicit)
const REPO_TAB_TO_KIND = {
  agents: 'agent',
  skills: 'skill',
  commands: 'command',
  rules: 'rule',
};
const KIND_TO_REPO_TAB = Object.fromEntries(
  Object.entries(REPO_TAB_TO_KIND).map(([t, k]) => [k, t]),
);

export function parsePath(path) {
  const parts = path.replace(/^\/|\/$/g, '').split('/').filter(Boolean);
  if (parts.length === 0) return { page: 'dashboard' };
  const [first, second, third, fourth] = parts;
  if (first === 'repos' && second) {
    const repoId = decodeURIComponent(second);
    if (third) {
      // Drill-in: /repos/:id/:tab/:name → render item detail in repo context
      if (fourth && REPO_TAB_TO_KIND[third]) {
        return {
          page: 'agent',
          repoId,
          kind: REPO_TAB_TO_KIND[third],
          name: decodeURIComponent(fourth),
        };
      }
      return { page: 'repo', repoId, tab: third };
    }
    return { page: 'repo', repoId, tab: 'overview' };
  }
  if (first === 'agents' && second) {
    return { page: 'agent', name: decodeURIComponent(second), kind: third || 'agent' };
  }
  return { page: first };  // top-level pages
}

// Exposed so RepoDetail/Sidebar can reason about kind ↔ tab mapping.
export { REPO_TAB_TO_KIND, KIND_TO_REPO_TAB };

// Route state → URL. Inverse of parsePath.
export function buildPath(route) {
  if (route.page === 'dashboard') return '/';
  if (route.page === 'repo') {
    const id = encodeURIComponent(route.repoId);
    const tab = route.tab && route.tab !== 'overview' ? `/${route.tab}` : '';
    return `/repos/${id}${tab}`;
  }
  if (route.page === 'agent') {
    const name = encodeURIComponent(route.name);
    // In-repo drill-in → /repos/:id/<tab>/:name
    if (route.repoId) {
      const tab = KIND_TO_REPO_TAB[route.kind] || 'agents';
      return `/repos/${encodeURIComponent(route.repoId)}/${tab}/${name}`;
    }
    // Global → /agents/:name[/:kind] (kind only for non-default 'skill' etc.)
    return route.kind && route.kind !== 'agent'
      ? `/agents/${name}/${route.kind}`
      : `/agents/${name}`;
  }
  return `/${route.page}`;
}

export function useRoute() {
  const [route, setRouteState] = useState(() => parsePath(window.location.pathname));

  useEffect(() => {
    const onPop = () => setRouteState(parsePath(window.location.pathname));
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const setRoute = useCallback((next) => {
    const path = buildPath(next);
    if (path !== window.location.pathname) {
      window.history.pushState(null, '', path);
    }
    setRouteState(next);
  }, []);

  // In-app "Back" buttons: walk the history stack instead of pushing a fresh
  // entry so the back button trail stays intuitive. Falls back to a plain
  // setRoute when there is no prior in-app history (e.g. user opened a deep
  // link in a fresh tab).
  const goBack = useCallback((fallbackRoute) => {
    if (window.history.length > 1 && document.referrer.startsWith(window.location.origin)) {
      window.history.back();
    } else {
      setRoute(fallbackRoute);
    }
  }, [setRoute]);

  return [route, setRoute, goBack];
}
