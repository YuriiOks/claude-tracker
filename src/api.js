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

function useFetch(path, fallback) {
  const [data, setData] = useState(fallback);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(!USE_MOCKS);

  useEffect(() => {
    if (USE_MOCKS) {
      setData(fallback);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetch(path, { headers: { Accept: 'application/json' } })
      .then(r => {
        if (!r.ok) throw new Error(`${r.status} ${path}`);
        return r.json();
      })
      .then(j => {
        if (!cancelled) {
          setData(j);
          setError(null);
          setLoading(false);
        }
      })
      .catch(e => {
        if (!cancelled) {
          // Fall back to mock so the UI is never empty.
           
          console.warn('[api] falling back to mock for', path, e?.message);
          setData(fallback);
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

// Sidebar identity. Falls back to mock USER until /api/user is wired up.
export function useUser() {
  return useFetch('/api/user', MOCK.USER);
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
