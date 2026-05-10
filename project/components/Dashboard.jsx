// Dashboard

const Dashboard = ({ repos, sessions, liveEvents, onOpen }) => {
  const totals = repos.reduce((a, r) => ({
    sessions: a.sessions + r.stats.sessionsToday,
    tokens: a.tokens + r.stats.tokensWeek,
    cost: a.cost + r.stats.costWeek,
    edits: a.edits + r.stats.filesEdited,
  }), { sessions: 0, tokens: 0, cost: 0, edits: 0 });
  const activeCount = repos.filter(r => r.isActive).length;
  const liveSessions = sessions.filter(s => s.status === 'running').length;

  // Filters for terminal
  const [feedFilter, setFeedFilter] = React.useState('all');
  const [feedPaused, setFeedPaused] = React.useState(false);
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
          <button className="btn btn-ghost"><Icon name="plug" size={12} />Add repo</button>
          <button className="btn primary"><Icon name="terminal" size={12} />Open live feed</button>
        </>}
      />

      <div className="grid grid-cols-4 mb-4">
        <Metric
          label="sessions today"
          value={totals.sessions}
          delta="+18%"
          deltaLabel="vs yesterday"
          accent="cyan"
        />
        <Metric
          label="tokens this week"
          value={(totals.tokens / 1e6).toFixed(2)}
          unit="M"
          delta="+2.1M"
          deltaLabel="projected eow"
          accent="gold"
        />
        <Metric
          label="spend this week"
          prefix="$"
          value={parseFloat(totals.cost.toFixed(2))}
          delta="-12%"
          deltaLabel="vs last week"
          accent="green"
        />
        <Metric
          label="active in editor"
          value={activeCount}
          delta={`${activeCount}`}
          deltaLabel="repos live now"
          accent="purple"
        />
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
                  <span className="repo-spark"><InlineSpark seed={r.id} accent={r.isActive?'green':'cyan'} showDot={r.isActive} /></span>
                  <span className="repo-sessions" title="Sessions today">{r.stats.sessionsToday}<span className="u">s</span></span>
                  <span className="repo-cost mono">${r.stats.costWeek.toFixed(2)}</span>
                  <Icon name="chevronRight" size={11} />
                </button>
              ))}
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
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

window.Dashboard = Dashboard;
