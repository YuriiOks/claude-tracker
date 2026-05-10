// HTML5 History API router. Replaces useState({page:'dashboard'}) so each
// page/repo/agent gets a unique URL, browser back/forward work, and deep
// links survive refresh.
import { useState, useEffect, useCallback } from 'react';

// URL → route state. Inverse of buildPath. See plan for full mapping.
export function parsePath(path) {
  const parts = path.replace(/^\/|\/$/g, '').split('/').filter(Boolean);
  if (parts.length === 0) return { page: 'dashboard' };
  const [first, second, third] = parts;
  if (first === 'repos' && second) {
    return { page: 'repo', repoId: decodeURIComponent(second) };
  }
  if (first === 'agents' && second) {
    return { page: 'agent', name: decodeURIComponent(second), kind: third || 'agent' };
  }
  return { page: first };  // /repos, /agents, /live, /sessions, /heatmap, etc.
}

// Route state → URL. Inverse of parsePath.
export function buildPath(route) {
  if (route.page === 'dashboard') return '/';
  if (route.page === 'repo') {
    return `/repos/${encodeURIComponent(route.repoId)}`;
  }
  if (route.page === 'agent') {
    const name = encodeURIComponent(route.name);
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
