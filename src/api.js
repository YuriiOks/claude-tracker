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

// R-SEC-10: permissions payloads (and the pairing token) are sensitive/
// short-lived — never let them land in sessionStorage.
function _isCacheExempt(path) {
  return path.startsWith('/api/permissions') || path.startsWith('/api/auth/pairing');
}

function _readCache(path) {
  if (typeof sessionStorage === 'undefined' || _isCacheExempt(path)) return null;
  try {
    const raw = sessionStorage.getItem(CACHE_PREFIX + path);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
function _writeCache(path, value) {
  if (typeof sessionStorage === 'undefined' || _isCacheExempt(path)) return;
  try { sessionStorage.setItem(CACHE_PREFIX + path, JSON.stringify(value)); } catch { /* quota or private mode */ }
}

// ── Pairing token ────────────────────────────────────────────────────────────
// Requests from localhost need no token; everything else (e.g. a phone on the
// LAN) needs `X-Tracker-Token` on fetches and `?token=` on WS URLs. The token
// is captured from a `?pair=<token>` URL param (see src/usePairing.js) and
// persisted in localStorage so it survives reloads.
const TOKEN_KEY = 'ct-auth-token';

export function getAuthToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setAuthToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* private mode */ }
}

function _authHeaders(extra) {
  const token = getAuthToken();
  return token ? { ...extra, 'X-Tracker-Token': token } : { ...extra };
}

// Every plain-object REST call in this file goes through here so the token
// header is attached consistently. A 401 flips the shared backend-status
// pub/sub to 'auth' instead of the generic offline/stale states.
async function apiFetch(path, opts = {}) {
  const res = await fetch(path, { ...opts, headers: _authHeaders(opts.headers) });
  if (res.status === 401) _setBackendState('auth');
  return res;
}

// Appends `?token=` (or `&token=` if the URL already has a query string) so
// WebSocket connections carry the pairing token the same way fetches do.
function _wsUrl(path) {
  const token = getAuthToken();
  if (!token) return path;
  return path + (path.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token);
}

// Localhost-only endpoint that mints a fresh pairing token. Used by the
// Tweaks panel's "Pair a phone" section — throws (and the caller should
// swallow it) when called from a non-localhost origin.
export async function fetchPairingToken() {
  const r = await apiFetch('/api/auth/pairing', { headers: { Accept: 'application/json' } });
  if (!r.ok) throw new Error(`${r.status} /api/auth/pairing`);
  const j = await r.json();
  return j.token;
}

// ── Backend reachability status ─────────────────────────────────────────────
// Tiny pub/sub (mirrors _liveStatus below) so any component can render an
// "is this real data?" signal without every useFetch call threading extra
// props through. useFetch() below is the sole writer via _reportFetchResult.
//   'mock'    — VITE_USE_MOCKS=1, never touches the network
//   'offline' — the most recent fetch failed and we've never had a success
//               this session (or the last success predates the last failure)
//   'stale'   — serving a sessionStorage cache from a previous successful
//               session but this session hasn't had a fresh success yet
//   'auth'    — the backend requires a pairing token we don't have (401)
//   'online'  — at least one fetch has succeeded and nothing has failed since
let _backendState = USE_MOCKS ? 'mock' : 'offline';
let _lastOkAt = null;
// True once ANY path has a sessionStorage cache from a prior successful run —
// used to distinguish "offline, never worked" from "offline, but we have
// something cached to show".
let _hasAnyCache = false;
if (!USE_MOCKS && typeof sessionStorage !== 'undefined') {
  try {
    for (let i = 0; i < sessionStorage.length; i++) {
      if (sessionStorage.key(i)?.startsWith(CACHE_PREFIX)) { _hasAnyCache = true; break; }
    }
  } catch { /* ignore */ }
}
const _backendSubs = new Set();
function _setBackendState(s) {
  if (_backendState === s) return;
  _backendState = s;
  _backendSubs.forEach(fn => fn({ state: _backendState, lastOkAt: _lastOkAt }));
}
function _reportFetchResult(ok) {
  if (USE_MOCKS) return;
  _setRetrying(false);
  if (ok) {
    _lastOkAt = Date.now();
    _setBackendState('online');
  } else {
    // The most recent result wins: a failure always degrades the state,
    // even from 'online' — otherwise a backend that dies after the first
    // successful load stays marked 'online' forever and the offline pill
    // never appears.
    _setBackendState(_hasAnyCache ? 'stale' : 'offline');
  }
}
// A 401 is not "the backend is down" — it's "the backend is fine but wants
// the pairing token". Keep it a distinct pub/sub state so the UI can say
// "pair this device" instead of "offline".
function _reportAuthRequired() {
  if (USE_MOCKS) return;
  _setRetrying(false);
  _setBackendState('auth');
}

export function useBackendStatus() {
  const [s, setS] = useState({ state: _backendState, lastOkAt: _lastOkAt });
  useEffect(() => {
    _backendSubs.add(setS);
    return () => _backendSubs.delete(setS);
  }, []);
  return s;
}

// Bumped by retryFetches() below; useFetch subscribes so a single "Retry"
// action in the UI re-triggers every mounted fetch hook at once.
let _retryVersion = 0;
const _retrySubs = new Set();

// True from the moment retryFetches() fires until the first fetch result
// (success or failure) comes back in — gives the UI an in-flight guard so
// "Retry" can't be mashed while a round is still outstanding.
let _retrying = false;
const _retryingSubs = new Set();
function _setRetrying(v) {
  if (_retrying === v) return;
  _retrying = v;
  _retryingSubs.forEach(fn => fn(_retrying));
}

export function useRetrying() {
  const [v, setV] = useState(_retrying);
  useEffect(() => {
    _retryingSubs.add(setV);
    return () => _retryingSubs.delete(setV);
  }, []);
  return v;
}

export function retryFetches() {
  _retryVersion += 1;
  _setRetrying(true);
  _retrySubs.forEach(fn => fn(_retryVersion));
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
  const [retryVersion, setRetryVersion] = useState(_retryVersion);

  useEffect(() => {
    _retrySubs.add(setRetryVersion);
    return () => _retrySubs.delete(setRetryVersion);
  }, []);

  useEffect(() => {
    if (USE_MOCKS) {
      setData(fallback);
      setLoading(false);
      return;
    }
    if (!path) {
      // Caller disabled the fetch (e.g. useFile with empty args)
      setData(fallback);
      setLoading(false);
      return;
    }
    let cancelled = false;
    // Path changed - drop the previous path's payload immediately so the UI
    // doesn't show stale data while the new fetch is in flight. Seed from the
    // new path's own cache if one exists, otherwise fall back.
    const pathCached = _readCache(path);
    setData(pathCached !== null ? pathCached : fallback);
    setError(null);
    setLoading(pathCached === null);
    apiFetch(path, { headers: { Accept: 'application/json' } })
      .then(r => {
        if (r.status === 401) {
          const e = new Error(`401 ${path}`);
          e.authRequired = true;
          throw e;
        }
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
            _hasAnyCache = true;
          }
          setError(null);
          setLoading(false);
          _reportFetchResult(true);
        }
      })
      .catch(e => {
        if (!cancelled) {
          // eslint-disable-next-line no-console
          console.warn('[api] fetch failed for', path, e?.message);
          // Keep whatever we already had (cache or initial fallback).
          setError(e);
          setLoading(false);
          if (e.authRequired) _reportAuthRequired();
          else _reportFetchResult(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [path, retryVersion]); // eslint-disable-line react-hooks/exhaustive-deps

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
// Throws an Error with .stale=true on a plain 409 (file changed on disk), or
// .needsConfirmation=true + .dangerous=[...] when the backend flagged one or
// more rules as dangerous (R-SEC-4) — resend with confirmDangerous:true only
// after the user explicitly confirms.
export async function updateScopedPermissions({ scope, target, permissions, ifUnchangedSince, confirmDangerous }) {
  const body = { scope, target, permissions, ifUnchangedSince };
  if (confirmDangerous) body.confirmDangerous = true;
  const r = await apiFetch("/api/permissions/scoped", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (r.status === 409) {
    const payload = await r.json().catch(() => ({}));
    if (payload.detail === "confirmation required") {
      const err = new Error("dangerous rule(s) require confirmation");
      err.needsConfirmation = true;
      err.dangerous = payload.dangerous || [];
      throw err;
    }
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
        const r = await apiFetch('/api/stats/dashboard');
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

// Heatmap — 7×24 session-count grid. Polls every 60s (changes slowly).
export function useHeatmap(intervalMs = 60000) {
  // Pass browser timezone so the backend buckets sessions in local time.
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (USE_MOCKS) { setLoading(false); return; }
    let cancelled = false;
    let timer;
    const tick = async () => {
      try {
        const r = await apiFetch(`/api/stats/heatmap?tz=${encodeURIComponent(tz)}`);
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
  }, [intervalMs, tz]);
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
  const res = await apiFetch('/api/repos', {
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
  const res = await apiFetch(`/api/repos/${encodeURIComponent(repoId)}`, { method: 'DELETE' });
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
        const r0 = MOCK.REPOS[0];
        const r1 = MOCK.REPOS[1] || MOCK.REPOS[0];
        setAgents([
          {
            sessionId: 'm1',
            repo: r0.id,
            agent: r0.agents?.[0] ?? 'agent',
            currentTool: ['Read', 'Edit', 'Bash'][Math.floor(t / 2000) % 3],
            currentTarget: r0.agents?.[0] ? `.claude/agents/${r0.agents[0]}.md` : 'src/index.js',
            secondsSinceLastEvent: Math.floor((t % 2000) / 200),
            elapsedSec: 124,
            startedAt: new Date(Date.now() - 124000).toISOString(),
          },
          {
            sessionId: 'm2',
            repo: r1.id,
            agent: r1.agents?.[1] ?? r1.agents?.[0] ?? 'agent',
            currentTool: 'Bash',
            currentTarget: r1.agents?.[1] ? `.claude/agents/${r1.agents[1]}.md` : 'src/app.js',
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
        const r = await apiFetch('/api/live/agents');
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
// Repo-scoped recent events (one-shot REST, no WS — used by RepoOverview).
// Polls every 5s so newly-arrived sessions surface without a full refresh.
export function useRepoEvents(repoId, n = 60, intervalMs = 5000) {
  const [events, setEvents] = useState([]);
  useEffect(() => {
    if (!repoId) { setEvents([]); return; }
    if (USE_MOCKS) { setEvents(MOCK.LIVE_EVENTS_SEED.filter(e => e.repo === repoId)); return; }
    let cancelled = false;
    let timer;
    const tick = async () => {
      try {
        const r = await apiFetch(`/api/live/recent?n=${n}&repo=${encodeURIComponent(repoId)}`);
        if (!r.ok) throw new Error(`${r.status}`);
        const j = await r.json();
        if (!cancelled) setEvents(j);
      } catch {
        /* network blip — keep last good snapshot */
      } finally {
        if (!cancelled) timer = setTimeout(tick, intervalMs);
      }
    };
    tick();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [repoId, n, intervalMs]);
  return events;
}

// ── Telemetry / OpenTelemetry hooks ──────────────────────────────────────────

// Current telemetry config (enabled flag, ingest URL, options, event total).
export function useTelemetryConfig() {
  return useFetch('/api/telemetry', MOCK.TELEMETRY_CONFIG);
}

// Imperative PUT — mirrors updateScopedPermissions.
// Returns the updated config (same shape as GET + backupPath).
// Throws Error with .stale=true on 409.
export async function setTelemetry({ enabled, logToolDetails, logUserPrompts, ifUnchangedSince }) {
  const r = await apiFetch('/api/telemetry', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled, logToolDetails, logUserPrompts, ifUnchangedSince }),
  });
  if (r.status === 409) {
    const err = new Error('telemetry settings changed on disk');
    err.stale = true;
    throw err;
  }
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`save failed: ${r.status} ${text}`);
  }
  return r.json();
}

// Imperative GET for refetching after a 409 stale conflict.
export async function getTelemetry() {
  const r = await apiFetch('/api/telemetry', { headers: { Accept: 'application/json' } });
  if (!r.ok) throw new Error(`${r.status} /api/telemetry`);
  return r.json();
}

// OTel summary (counts, errors, tool latency). Polls every intervalMs.
// Seeded with MOCK.OTEL_SUMMARY only in mock mode -- in real mode this must
// start empty so a broken/unreachable backend can never be mistaken for a
// live telemetry read (see loading/error below).
export function useOtelSummary(intervalMs = 10000) {
  const [data, setData] = useState(USE_MOCKS ? MOCK.OTEL_SUMMARY : null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(!USE_MOCKS);
  useEffect(() => {
    if (USE_MOCKS) { setLoading(false); return; }
    let cancelled = false;
    let timer;
    const tick = async () => {
      try {
        const r = await apiFetch('/api/otel/summary?hours=24');
        if (!r.ok) throw new Error(`${r.status}`);
        const j = await r.json();
        if (!cancelled) { setData(j); setError(null); setLoading(false); }
      } catch (e) {
        if (!cancelled) { setError(e); setLoading(false); }
      }
      if (!cancelled) timer = setTimeout(tick, intervalMs);
    };
    tick();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [intervalMs]);
  return { data, error, loading };
}

// OTel metrics (cost, tokens, sessions, activeTimeSec). Polls every intervalMs.
// Seeded with MOCK.OTEL_METRICS only in mock mode -- in real mode this must
// start empty so a broken/unreachable backend can never be mistaken for a
// live telemetry read (see loading/error below).
export function useOtelMetrics(intervalMs = 10000) {
  const [data, setData] = useState(USE_MOCKS ? MOCK.OTEL_METRICS : null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(!USE_MOCKS);
  useEffect(() => {
    if (USE_MOCKS) { setLoading(false); return; }
    let cancelled = false;
    let timer;
    const tick = async () => {
      try {
        const r = await apiFetch('/api/otel/metrics?hours=24');
        if (!r.ok) throw new Error(`${r.status}`);
        const j = await r.json();
        if (!cancelled) { setData(j); setError(null); setLoading(false); }
      } catch (e) {
        if (!cancelled) { setError(e); setLoading(false); }
      }
      if (!cancelled) timer = setTimeout(tick, intervalMs);
    };
    tick();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [intervalMs]);
  return { data, error, loading };
}

// Recent OTel events list (one-shot, no polling).
export function useOtelEvents(n = 200, kind = '') {
  const qs = kind ? `?n=${n}&kind=${encodeURIComponent(kind)}` : `?n=${n}`;
  return useFetch(`/api/otel/events${qs}`, MOCK.OTEL_EVENTS);
}

// Live-connection status, shared across every useLiveEvents() consumer via a
// tiny pub/sub -- useLiveEvents() itself keeps returning a plain array so
// existing consumers (App.jsx, Dashboard) are untouched; screens that want
// the status (e.g. LivePage) opt in via useLiveStatus().
let _liveStatus = 'polling';
const _statusSubs = new Set();
function _setLiveStatus(s) { _liveStatus = s; _statusSubs.forEach(fn => fn(s)); }

export function useLiveStatus() {
  const [s, setS] = useState(_liveStatus);
  useEffect(() => {
    _statusSubs.add(setS);
    return () => _statusSubs.delete(setS);
  }, []);
  return s;
}

// Build a dedup key for an event. `id` alone is not a safe key: REST rows
// stamp it from the DB pk while WS rows stamp it from a per-process seq that
// resets on backend restart -- different numbering spaces that can collide
// and silently drop events. Always key on payload identity instead (mirrors
// NebulaGraph.jsx's eventDedupKey).
function _eventKey(e) {
  return `${e.ts ?? e.t}|${e.kind}|${e.tool ?? e.to ?? e.skill ?? e.cmd ?? ''}|${e.target ?? ''}`;
}

// Map an event to a comparable number for chronological sort. Real backend
// rows carry `ts` as an ISO-8601 string (Date.parse -> ms epoch); a bare
// number is used as-is. Mock rows have no `ts`, only a relative numeric `t`
// (seconds-from-now) -- fall back to that, and to 0 if neither is present.
function _eventTime(e) {
  if (e.ts != null) return typeof e.ts === 'number' ? e.ts : Date.parse(e.ts);
  return e.t ?? 0;
}

export function useLiveEvents() {
  const [events, setEvents] = useState(USE_MOCKS ? MOCK.LIVE_EVENTS_SEED.map(e => ({ ...e })) : []);
  const tickRef = useRef(0);
  const seenRef = useRef(new Set());

  // Mock cycle (preserves the original demo behaviour).
  useEffect(() => {
    if (!USE_MOCKS) return undefined;
    _setLiveStatus('mock');
    const speedMap = { slow: 5500, normal: 2400, fast: 900 };
    let timer;
    // Recursive setTimeout (not setInterval) so each tick re-reads
    // window.__tweakSpeed for its own delay -- a speed change from the
    // tweaks panel takes effect on the next tick instead of needing reload.
    const tick = () => {
      tickRef.current += 1;
      const idx = (tickRef.current - 1) % MOCK.LIVE_EVENTS_FUTURE.length;
      const e = MOCK.LIVE_EVENTS_FUTURE[idx];
      setEvents(prev => {
        const next = [...prev, { ...e, t: prev.length > 0 ? prev[prev.length - 1].t + (e.dt || 3) : 0 }];
        return next.slice(-60);
      });
      const speed = window.__tweakSpeed || 'normal';
      timer = setTimeout(tick, speedMap[speed] || 2400);
    };
    const initialSpeed = window.__tweakSpeed || 'normal';
    timer = setTimeout(tick, speedMap[initialSpeed] || 2400);
    return () => clearTimeout(timer);
  }, []);

  // Real backend: cold-start + WS.
  useEffect(() => {
    if (USE_MOCKS) return undefined;
    let ws;
    let cancelled = false;
    let backoff = 1000;
    let isFirstOpen = true;

    _setLiveStatus('polling');

    // Shared by cold-start and reconnect: append only unseen rows, sort by
    // timestamp, cap the ring buffer. On an empty buffer this degenerates to
    // a plain load, so the happy-path behaviour is unchanged.
    const mergeRows = (rows) => {
      setEvents(prev => {
        const merged = [...prev];
        for (const row of rows) {
          const k = _eventKey(row);
          if (seenRef.current.has(k)) continue;
          seenRef.current.add(k);
          merged.push(row);
        }
        merged.sort((a, b) => _eventTime(a) - _eventTime(b));
        return merged.slice(-60);
      });
    };

    apiFetch('/api/live/recent?n=60')
      .then(r => {
        if (r.status === 401) _reportAuthRequired();
        return r.ok ? r.json() : [];
      })
      .then(j => {
        if (cancelled) return;
        mergeRows(Array.isArray(j) ? j : []);
      })
      .catch(() => {});

    const connect = () => {
      if (cancelled) return;
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(_wsUrl(`${proto}//${window.location.host}/ws/live`));
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          const k = _eventKey(data);
          if (seenRef.current.has(k)) return;
          seenRef.current.add(k);
          if (seenRef.current.size > 1000) {
            seenRef.current = new Set([...seenRef.current].slice(-300));
          }
          setEvents(prev => [...prev, data].slice(-60));
        } catch { /* ignore */ }
      };
      ws.onopen = () => {
        backoff = 1000;
        _setLiveStatus('live');
        if (isFirstOpen) {
          isFirstOpen = false;
          return;
        }
        // Composite keys are stable across REST and WS sources (no id-space
        // collisions), so a reconnect only needs the merge-fetch to backfill
        // whatever the WS gap dropped -- no key surgery required first.
        apiFetch('/api/live/recent?n=60')
          .then(r => (r.ok ? r.json() : []))
          .then(rows => {
            if (cancelled || !Array.isArray(rows)) return;
            mergeRows(rows);
          })
          .catch(() => {});
      };
      ws.onclose = (ev) => {
        if (cancelled) return;
        // AUTH CONTRACT: the backend closes with 4401 when the pairing token
        // is missing/invalid. That's not a transient network blip -- retrying
        // with the same (bad) token would just loop, so surface 'auth'
        // instead of grinding through the reconnect/backoff ladder.
        if (ev.code === 4401) {
          _reportAuthRequired();
          _setLiveStatus('reconnecting');
          return;
        }
        _setLiveStatus('reconnecting');
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
