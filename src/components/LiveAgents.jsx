import { useActiveAgents } from '../api';
import Icon from '../icons';
import { fmtSince } from '../utils/time';

const ACCENT_BY_REPO = {};
function dotColor(repo, accent) {
  if (accent) return accent;
  if (!ACCENT_BY_REPO[repo]) {
    const palette = ['#d97757', '#5a8dee', '#a78bfa', '#10b981', '#f59e0b', '#ef4444', '#22d3ee'];
    const idx = Math.abs([...repo].reduce((a, c) => a + c.charCodeAt(0), 0)) % palette.length;
    ACCENT_BY_REPO[repo] = palette[idx];
  }
  return ACCENT_BY_REPO[repo];
}

function fmtElapsed(s) {
  if (s == null) return '';
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m < 1) return `${s}s`;
  if (m < 60) return `${m}m ${String(r).padStart(2, '0')}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

export default function LiveAgents({ repos = [] }) {
  const agents = useActiveAgents();

  const repoMap = Object.fromEntries(repos.map(r => [r.id || r.name, r]));

  return (
    <div>
      <div className="la-header">
        <h2 className="section-title"><Icon name="zap" />Currently active</h2>
        <span className="la-count">{agents.length} session{agents.length === 1 ? '' : 's'}</span>
      </div>

      {agents.length === 0 ? (
        <div className="la-empty">
          No active sessions. Run <code>claude</code> in any tracked repo and you&rsquo;ll see it appear here within ~2s.
        </div>
      ) : (
        <div className="la-grid">
          {agents.map(a => {
            const since = a.secondsSinceLastEvent ?? 0;
            const isFresh = since <= 2;
            const isStale = since > 30;
            const repoMeta = repoMap[a.repo];
            const color = dotColor(a.repo, repoMeta?.accent);
            const dotClass = since <= 2 ? 'live-fast' : since <= 10 ? 'live-slow' : '';

            return (
              <div
                key={a.sessionId}
                className={`la-row ${isFresh ? 'is-fresh' : ''} ${isStale ? 'is-stale' : ''}`}
                title={`session ${a.sessionId} · started ${fmtElapsed(a.elapsedSec)} ago`}
              >
                <span className="la-dot-wrap" style={{ color }}>
                  <span className={`la-dot ${dotClass}`}></span>
                </span>
                <span className="la-repo">{a.repo}</span>
                <span className="la-agent">
                  <Icon name="bot" size={11} />&nbsp;{a.agent || 'main'}
                </span>
                <span className="la-tool">
                  {a.currentTool ? (
                    <>
                      <b>{a.currentTool}</b>
                      {a.currentTarget && <> &middot; <span className="la-target">{a.currentTarget}</span></>}
                    </>
                  ) : (
                    <em style={{ opacity: .6 }}>thinking…</em>
                  )}
                </span>
                <span className="la-elapsed">{fmtSince(since)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
