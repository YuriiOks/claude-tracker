import { useActiveAgents } from '../api';
import Icon from '../icons';

const STYLES = `
@keyframes lp-pulse-fast {
  0%, 100% { transform: scale(1);   opacity: 1;    box-shadow: 0 0 0 0   currentColor; }
  50%      { transform: scale(1.6); opacity: .55;  box-shadow: 0 0 0 6px transparent; }
}
@keyframes lp-pulse-slow {
  0%, 100% { transform: scale(1);   opacity: .9;   box-shadow: 0 0 0 0   currentColor; }
  50%      { transform: scale(1.3); opacity: .55;  box-shadow: 0 0 0 4px transparent; }
}
@keyframes lp-shimmer {
  0%   { background-position: -200% 0; }
  100% { background-position:  200% 0; }
}

.la-grid { display: flex; flex-direction: column; gap: .5rem; }

.la-row {
  display: grid;
  grid-template-columns: 18px 110px 160px 1fr 78px;
  align-items: center;
  gap: .8rem;
  padding: .55rem .8rem;
  border: 1px solid var(--bord, #2a2f3a);
  border-radius: 6px;
  background: var(--surface, rgba(255,255,255,.02));
  font-family: ui-monospace, "Fira Code", monospace;
  font-size: .76rem;
  position: relative;
  overflow: hidden;
}
.la-row.is-fresh::before {
  content: '';
  position: absolute; inset: 0;
  background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,.04) 50%, transparent 100%);
  background-size: 200% 100%;
  animation: lp-shimmer 2.4s linear infinite;
  pointer-events: none;
}
.la-row.is-stale { opacity: .55; }

.la-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: currentColor;
  display: inline-block;
}
.la-dot.live-fast { animation: lp-pulse-fast 0.65s ease-in-out infinite; }
.la-dot.live-slow { animation: lp-pulse-slow 1.6s  ease-in-out infinite; }

.la-repo  { font-weight: 600; color: var(--txt-bright, #e6edf3); }
.la-agent { color: var(--accent, #6cd0ff); font-weight: 600; }
.la-tool  { color: var(--muted, #8a93a3); }
.la-tool b { color: var(--txt, #c8d0db); font-weight: 500; }
.la-target {
  color: var(--muted, #8a93a3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: .7rem;
}
.la-elapsed {
  text-align: right;
  color: var(--muted, #8a93a3);
  font-size: .68rem;
}

.la-empty {
  padding: 1.2rem;
  text-align: center;
  color: var(--muted, #8a93a3);
  font-size: .82rem;
  border: 1px dashed var(--bord, #2a2f3a);
  border-radius: 6px;
}

.la-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: .5rem;
}
.la-count {
  font-family: ui-monospace, monospace; font-size: .68rem;
  padding: 2px 8px; border-radius: 999px;
  background: rgba(108, 208, 255, .12);
  color: var(--accent, #6cd0ff);
}
`;

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

function fmtSince(s) {
  if (s == null) return '—';
  if (s < 1) return 'now';
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m ago` : `${Math.floor(m / 60)}h ago`;
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
      <style>{STYLES}</style>
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
