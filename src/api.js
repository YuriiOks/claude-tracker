/**
 * Backend client. Provides one hook per resource, with mock fallback when
 * VITE_USE_MOCKS=1 OR the backend is unreachable.
 *
 * Wire format mirrors src/data.js exactly (Pydantic camelCase aliases on the
 * server). Every component should import from here, not from ./data.
 */
import { useEffect, useRef, useState } from 'react';
import * as MOCK from './data';

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === '1';

// sessionStorage cache key per path. Persists real data across reloads so the
// UI hydrates with the LAST seen real response — no mock-fallback flash.
const CACHE_PREFIX = 'ct:fetch:';

function _readCache(path) {
  if (typeof sessionStorage === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem(CACHE_PREFIX + path);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
function _writeCache(path, value) {
  if (typeof sessionStorage === 'undefined') return;
  try { sessionStorage.setItem(CACHE_PREFIX + path, JSON.stringify(value)); } catch { /* quota or private mode */ }
}

function useFetch(path, fallback) {
  // Initial value priority:
  //  1. sessionStorage cached real response (no flash on reload)
  //  2. fallback (mock data — keeps the UI shape so components don't crash on null)
  // Components that care about "is this real data?" can read `loading`.
  const cached = _readCache(path);
  const [data, setData] = useState(cached !== null ? cached : fallback);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(!USE_MOCKS && cached === null);

  useEffect(() => {
    if (USE_MOCKS) {
      setData(fallback);
      setLoading(false);
      return;
    }
    if (!path) {
      // Caller disabled the fetch (e.g. useFile with empty args)
      setLoading(false);
      return;
    }
    let cancelled = false;
    if (_readCache(path) === null) setLoading(true);
    fetch(path, { headers: { Accept: 'application/json' } })
      .then(r => {
        if (!r.ok) throw new Error(`${r.status} ${path}`);
        return r.json();
      })
      .then(j => {
        if (!cancelled) {
          // Preserve the fallback when the backend returns null/undefined —
          // that signals "feature not wired yet", and overwriting the mock
          // makes the route read as if the page doesn't exist. Legitimate
          // empty results ([], {}) are still passed through so consumers can
          // distinguish "no data right now" from "no backend response".
          if (j != null) {
            setData(j);
            _writeCache(path, j);
          }
          setError(null);
          setLoading(false);
        }
      })
      .catch(e => {
        if (!cancelled) {
          // eslint-disable-next-line no-console
          console.warn('[api] fetch failed for', path, e?.message);
          // Keep whatever we already had (cache or initial fallback).
          setError(e);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [path]); // eslint-disable-line react-hooks/exhaustive-deps

  return { data, error, loading };
}

export function useRepos() {
  return useFetch('/api/repos', MOCK.REPOS);
}

export function useGlobal() {
  const fallback = { ...MOCK.GLOBAL, fileSizes: MOCK.FILE_SIZES };
  return useFetch('/api/global', fallback);
}

export function useFileSizes() {
  const { data } = useGlobal();
  return data?.fileSizes ?? MOCK.FILE_SIZES;
}

export function useSessions(limit = 50) {
  return useFetch(`/api/sessions?limit=${limit}`, MOCK.SESSIONS);
}

export function useAgents() {
  return useFetch('/api/agents', MOCK.AGENT_META);
}

export function usePermissions() {
  return useFetch('/api/permissions', MOCK.PERMISSIONS_DETAIL);
}

// Scoped permissions editor — reads from one specific settings file
// (committed settings.json OR gitignored settings.local.json) and
// returns the file metadata too (path, exists, mtime) so the UI can
// detect external edits when the user saves.
export function useScopedPermissions(scope = "global", target = "settings_local") {
  const fallback = { scope, target, filePath: "", fileExists: false, mtime: 0, permissions: { allow: [], deny: [], ask: [] } };
  const qs = new URLSearchParams({ scope, target }).toString();
  return useFetch(`/api/permissions/scoped?${qs}`, fallback);
}

// One-shot PUT that replaces a single settings file's permissions block.
// Returns a promise that resolves to { filePath, mtime, backupPath }.
// Throws an Error with .stale=true on 409 so the caller can refresh.
export async function updateScopedPermissions({ scope, target, permissions, ifUnchangedSince }) {
  const r = await fetch("/api/permissions/scoped", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scope, target, permissions, ifUnchangedSince }),
  });
  if (r.status === 409) {
    const err = new Error("settings file changed on disk");
    err.stale = true;
    throw err;
  }
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`save failed: ${r.status} ${text}`);
  }
  return r.json();
}

export function usePlugins() {
  return useFetch('/api/plugins', { plugins: {}, names: [] });
}

export function useCost(days = 7) {
  const fallback = { byDay: [], byRepo: [], totalTokens: 0, totalCost: 0, windowDays: days };
  return useFetch(`/api/cost?days=${days}`, fallback);
}

export function useDiff() {
  return useFetch('/api/diffs/recent', MOCK.DIFF_SAMPLE);
}

// F13: Recent-diff feed shown on DiffPage. Mock fallback until backend lands.
export function useRecentDiffs() {
  return useFetch('/api/diffs/list', MOCK.RECENT_DIFFS);
}

// Drill into a specific file's current diff (click-to-load on DiffPage).
// `repo` is the repo dir name, `path` is the path relative to repo root.
// Returns null until both args are set so DiffPage can show the headline
// diff (useDiff) by default and only load this on demand.
export function useFileDiff(repo, path) {
  const enabled = Boolean(repo && path);
  const url = enabled ? `/api/diffs/file?repo=${encodeURIComponent(repo)}&path=${encodeURIComponent(path)}` : null;
  return useFetch(url, null);
}

// Dashboard stats — totals + deltas + 24-bucket sparklines per metric.
// Polls every 5s for a near-live feel.
export function useDashboardStats(intervalMs = 5000) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (USE_MOCKS) { setLoading(false); return; }
    let cancelled = false;
    let timer;
    const tick = async () => {
      try {
        const r = await fetch('/api/stats/dashboard');
        if (!r.ok) throw new Error(`${r.status}`);
        const j = await r.json();
        if (!cancelled) { setData(j); setLoading(false); }
      } catch {
        if (!cancelled) setLoading(false);
      }
      if (!cancelled) timer = setTimeout(tick, intervalMs);
    };
    tick();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [intervalMs]);
  return { data, loading };
}

// Sidebar identity. Backend returns only what it can discover (claudeVersion);
// the rest (name, email, initials) comes from MOCK.USER as defaults.
export function useUser() {
  const r = useFetch('/api/user', MOCK.USER);
  const merged = { ...MOCK.USER, ...(r.data || {}) };
  return { ...r, data: merged };
}

// Discovery of candidate repos (folders with .claude/ that aren't tracked yet).
export function useRepoCandidates() {
  return useFetch('/api/repos/candidates/list', []);
}

// POST a new repo path to the runtime registry. Throws on error.
export async function addRepo(hostPath) {
  const res = await fetch('/api/repos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: hostPath }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// List .html artifacts under a directory of a tracked repo. Defaults to docs/.
export function useRepoHtmlArtifacts(repoId, dir) {
  const qs = dir ? `?dir=${encodeURIComponent(dir)}` : '';
  const url = repoId ? `/api/repos/${encodeURIComponent(repoId)}/artifacts/html${qs}` : null;
  return useFetch(url, []);
}

// Fetch a .md/.html file from a tracked repo. Returns { content, path, size }
// or null while loading / on failure. Path is relative to the repo root.
export function useFile(repoId, relPath) {
  const enabled = Boolean(repoId && relPath);
  return useFetch(
    enabled ? `/api/files/${encodeURIComponent(repoId)}/${relPath.split('/').map(encodeURIComponent).join('/')}` : null,
    null,
  );
}

// DELETE a repo from the runtime registry (env entries can't be removed).
export async function removeRepo(repoId) {
  const res = await fetch(`/api/repos/${encodeURIComponent(repoId)}`, { method: 'DELETE' });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Currently-active agents — polls every 1.5s.
 * Each row: { sessionId, repo, agent, currentTool, currentTarget, startedAt,
 *             lastSeenAt, elapsedSec, secondsSinceLastEvent }
 */
export function useActiveAgents(intervalMs = 1500) {
  const [agents, setAgents] = useState([]);

  useEffect(() => {
    if (USE_MOCKS) {
      const cycle = () => {
        const t = Date.now() % 6000;
        setAgents([
          {
            sessionId: 'm1',
            repo: 'jupus',
            agent: 'ai-developer',
            currentTool: ['Read', 'Edit', 'Bash'][Math.floor(t / 2000) % 3],
            currentTarget: 'app/ai/services/chat/bedrock/stream_parser.py',
            secondsSinceLastEvent: Math.floor((t % 2000) / 200),
            elapsedSec: 124,
            startedAt: new Date(Date.now() - 124000).toISOString(),
          },
          {
            sessionId: 'm2',
            repo: 'anita',
            agent: 'rag-architect',
            currentTool: 'Bash',
            currentTarget: 'python eval_rag.py --model claude-haiku',
            secondsSinceLastEvent: 4,
            elapsedSec: 312,
            startedAt: new Date(Date.now() - 312000).toISOString(),
          },
        ]);
      };
      cycle();
      const id = setInterval(cycle, 1000);
      return () => clearInterval(id);
    }
    let cancelled = false;
    let timer;
    const tick = async () => {
      try {
        const r = await fetch('/api/live/agents');
        if (r.ok) {
          const j = await r.json();
          if (!cancelled) setAgents(Array.isArray(j) ? j : []);
        }
      } catch { /* ignore */ }
      if (!cancelled) timer = setTimeout(tick, intervalMs);
    };
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [intervalMs]);

  return agents;
}

/**
 * Live events.
 * Cold-start with /api/live/recent, then upgrade to a WebSocket /ws/live.
 * Falls back to MOCK.LIVE_EVENTS_SEED + cycling LIVE_EVENTS_FUTURE when
 * VITE_USE_MOCKS=1 or both REST + WS fail.
 */
export function useLiveEvents() {
  const [events, setEvents] = useState(USE_MOCKS ? MOCK.LIVE_EVENTS_SEED.map(e => ({ ...e })) : []);
  const tickRef = useRef(0);

  // Mock cycle (preserves the original demo behaviour).
  useEffect(() => {
    if (!USE_MOCKS) return undefined;
    const speedMap = { slow: 5500, normal: 2400, fast: 900 };
    const speed = window.__tweakSpeed || 'normal';
    const interval = speedMap[speed] || 2400;
    const id = setInterval(() => {
      tickRef.current += 1;
      const idx = (tickRef.current - 1) % MOCK.LIVE_EVENTS_FUTURE.length;
      const e = MOCK.LIVE_EVENTS_FUTURE[idx];
      setEvents(prev => {
        const next = [...prev, { ...e, t: prev.length > 0 ? prev[prev.length - 1].t + (e.dt || 3) : 0 }];
        return next.slice(-60);
      });
    }, interval);
    return () => clearInterval(id);
  }, []);

  // Real backend: cold-start + WS.
  useEffect(() => {
    if (USE_MOCKS) return undefined;
    let ws;
    let cancelled = false;
    let backoff = 1000;

    fetch('/api/live/recent?n=60')
      .then(r => (r.ok ? r.json() : []))
      .then(j => { if (!cancelled) setEvents(Array.isArray(j) ? j : []); })
      .catch(() => {});

    const connect = () => {
      if (cancelled) return;
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${proto}//${window.location.host}/ws/live`);
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          setEvents(prev => [...prev, data].slice(-60));
        } catch { /* ignore */ }
      };
      ws.onopen = () => { backoff = 1000; };
      ws.onclose = () => {
        if (cancelled) return;
        setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, 15000);
      };
      ws.onerror = () => { try { ws.close(); } catch { /* ignore */ } };
    };
    connect();

    return () => {
      cancelled = true;
      try { ws?.close(); } catch { /* ignore */ }
    };
  }, []);

  return events;
}
