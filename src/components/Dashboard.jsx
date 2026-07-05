import { useState } from 'react';
import { useDashboardStats } from '../api';
import Icon from '../icons';
import { Metric, Status, InlineSpark, PageHead } from './Common';
import LiveTerminal from './LiveTerminal';
import LiveAgents from './LiveAgents';
import { lazy, Suspense } from 'react';
const AddRepoModal = lazy(() => import('./AddRepoModal'));

const Dashboard = ({ repos, sessions, liveEvents, onOpen, setRoute, liveAgents }) => {
  const [addRepoOpen, setAddRepoOpen] = useState(false);
  // Real-time aggregate stats (polled every 5s)
  const { data: stats } = useDashboardStats();

  // Repo-side fallback (used until /api/stats/dashboard responds)
  const fallback = repos.reduce((a, r) => ({
    sessions: a.sessions + r.stats.sessionsToday,
    tokens: a.tokens + r.stats.tokensWeek,
    cost: a.cost + r.stats.costWeek,
    edits: a.edits + r.stats.filesEdited,
  }), { sessions: 0, tokens: 0, cost: 0, edits: 0 });
  const activeCount = repos.filter(r => r.isActive).length;

  // Format the delta percent → arrow + sign; clip huge ratios as `+22x`
  // so deltas like 5947% don't blow out the layout while still reading
  // as obviously-big.
  const fmtDelta = (pct) => {
    if (pct == null) return null;
    const abs = Math.abs(pct);
    const sign = pct < 0 ? '-' : '+';
    if (abs >= 1000) return `${sign}${(abs / 100).toFixed(0)}x`;
    if (abs >= 100)  return `${sign}${abs.toFixed(0)}%`;
    return `${sign}${abs.toFixed(1)}%`;
  };
  // Format a count into { value, unit } with B/M/k scale. Used for tokens
  // where the headline value can be billions when cache_read is included.
  const fmtCount = (n) => {
    if (n == null) return { v: '—', u: '' };
    if (n >= 1e9) return { v: (n / 1e9).toFixed(2), u: 'B' };
    if (n >= 1e6) return { v: (n / 1e6).toFixed(2), u: 'M' };
    if (n >= 1e3) return { v: (n / 1e3).toFixed(1), u: 'k' };
    return { v: String(n), u: '' };
  };

  // Real values when /api/stats/dashboard has responded; else fallback.
  // Chain all the way through — a response missing a sub-key (e.g. no
  // `sessions` object) must fall back, not throw past the single root
  // ErrorBoundary and take down the whole app.
  const sessionsToday = stats?.sessions?.today ?? fallback.sessions;
  const sessionsDelta = stats?.sessions ? fmtDelta(stats.sessions.deltaPct) : null;
  const tokensThisWeek = stats?.tokens?.thisWeek ?? fallback.tokens;
  const tokensDisplay  = fmtCount(tokensThisWeek);
  const tokensDelta    = stats?.tokens ? fmtDelta(stats.tokens.deltaPct) : null;
  const costThisWeek = stats?.cost?.thisWeek ?? fallback.cost;
  const costDelta = stats?.cost ? fmtDelta(stats.cost.deltaPct) : null;

  const [feedFilter, setFeedFilter] = useState('all');
  const [feedPaused, setFeedPaused] = useState(false);
  const filtered = feedFilter === 'all'
    ? liveEvents
    : liveEvents.filter(e => e.kind === feedFilter || (feedFilter === 'tool' && e.kind === 'command'));

  return (
    <>
      <PageHead
        eyebrow={<><span className="prompt">~/.claude</span><span className="sep">·</span>workspace overview</>}
        title="Workspace"
        sub="Live snapshot of every repo Claude Code is working in. Last refreshed just now."
        actions={<>
          <button
            className="btn btn-ghost"
            title="Discover and add a repo with a .claude/ folder"
            onClick={() => setAddRepoOpen(true)}
          >
            <Icon name="plug" size={12} />Add repo
          </button>
          <button
            className="btn primary"
            onClick={() => setRoute({ page: 'live' })}
          >
            <Icon name="terminal" size={12} />Open live feed
          </button>
        </>}
      />

      <div className="grid grid-cols-4 mb-4">
        <Metric
          label="sessions today"
          value={sessionsToday}
          delta={sessionsDelta}
          deltaLabel="vs yesterday"
          accent="cyan"
          points={stats?.sessions?.spark}
        />
        <Metric
          label="tokens this week"
          value={tokensDisplay.v}
          unit={tokensDisplay.u}
          delta={tokensDelta}
          deltaLabel="vs last week"
          accent="gold"
          points={stats?.tokens?.spark}
        />
        <Metric
          label="spend this week"
          prefix="$"
          value={costThisWeek.toFixed(2)}
          delta={costDelta}
          deltaLabel="vs last week"
          accent="green"
          points={stats?.cost?.spark}
        />
        <Metric
          label="active in editor"
          value={activeCount}
          delta={`${activeCount}`}
          deltaLabel="repos live now"
          accent="purple"
          points={stats?.active?.spark}
        />
      </div>

      <div className="mb-4">
        <LiveAgents repos={repos} onOpen={onOpen} agents={liveAgents} />
      </div>

      <div className="split mb-4">
        <div className="col gap-md">
          <div className="card-frame">
            <div className="card-frame-head">
              <h2 className="section-title"><Icon name="terminal" />Live activity</h2>
              <span className="frame-meta">{feedPaused ? '⏸ paused' : `● ${filtered.length} events`}</span>
              <div className="row gap-xs">
                <div className="seg">
                  <button className={feedFilter==='all'?'active':''} onClick={()=>setFeedFilter('all')}>All</button>
                  <button className={feedFilter==='agent_start'?'active':''} onClick={()=>setFeedFilter('agent_start')}>Agents</button>
                  <button className={feedFilter==='delegate'?'active':''} onClick={()=>setFeedFilter('delegate')}>Delegations</button>
                  <button className={feedFilter==='tool'?'active':''} onClick={()=>setFeedFilter('tool')}>Tools</button>
                  <button className={feedFilter==='skill'?'active':''} onClick={()=>setFeedFilter('skill')}>Skills</button>
                  <button className={feedFilter==='permission'?'active':''} onClick={()=>setFeedFilter('permission')}>Perms</button>
                </div>
                <button className={'icon-btn-sm' + (feedPaused?' active':'')} title={feedPaused?'Resume':'Pause'} onClick={()=>setFeedPaused(p=>!p)}>
                  <Icon name={feedPaused?'play':'pause'} size={11} />
                </button>
              </div>
            </div>
            <LiveTerminal events={filtered.slice(-22)} height={360} paused={feedPaused} hideHeader={true} />
          </div>
        </div>

        <div className="col gap-md">
          <div className="card-frame">
            <div className="card-frame-head">
              <h2 className="section-title"><Icon name="folder" />Active repositories</h2>
              <span className="frame-meta">{repos.length} tracked</span>
            </div>
            <div className="repo-list">
              {repos.map(r => (
                <button key={r.id} className={'repo-row' + (r.isActive ? ' live-row' : '')} onClick={() => onOpen(r.id)} style={{ '--accent': r.accent }}>
                  <span className={'sb-repo-dot' + (r.isActive ? ' live' : '')}></span>
                  <span className="repo-name">{r.name}</span>
                  <span className="repo-branch mono">{r.branch}</span>
                  <span className="repo-spark"><InlineSpark seed={r.id} accent={r.isActive?'green':'cyan'} showDot={r.isActive} points={r.stats?.spark} /></span>
                  <span className="repo-sessions" title="Sessions today">{r.stats.sessionsToday}<span className="u">s</span></span>
                  <span className="repo-cost mono">${r.stats.costWeek.toFixed(2)}</span>
                  <Icon name="chevronRight" size={11} />
                </button>
              ))}
              {repos.length === 0 && <div className="empty">No repos tracked yet.</div>}
            </div>
          </div>

          <div className="card-frame">
            <div className="card-frame-head">
              <h2 className="section-title"><Icon name="clock" />Recent sessions</h2>
              <button className="link-btn">View all →</button>
            </div>
            <div className="session-list">
              {sessions.slice(0, 5).map(s => (
                <div key={s.id} className="session-row">
                  <span className="session-time mono">{s.started}</span>
                  <div className="session-mid">
                    <div className="session-task">{s.task}</div>
                    <div className="session-meta">
                      <span className="agent-tag">{s.agent}</span>
                      <span className="dot-sep">·</span>
                      <span className="repo-name-mini">{s.repo}</span>
                    </div>
                  </div>
                  <Status kind={s.status} size="sm" />
                  <span className="session-cost mono">${s.cost.toFixed(2)}</span>
                </div>
              ))}
              {sessions.length === 0 && <div className="empty">No sessions recorded yet.</div>}
            </div>
          </div>
        </div>
      </div>
    {addRepoOpen && (
        <Suspense fallback={null}>
          <AddRepoModal
            onClose={() => setAddRepoOpen(false)}
            onAdded={() => {
              // Close + refresh — the next useRepos poll picks up the addition
              setAddRepoOpen(false);
              window.location.reload();
            }}
          />
        </Suspense>
      )}
    </>
  );
};

export default Dashboard;
