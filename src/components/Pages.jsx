import { useState } from 'react';
import Icon from '../icons';
import { Metric, Status, PageHead } from './Common';
import LiveTerminal from './LiveTerminal';
import LiveAgents from './LiveAgents';
import { usePermissions } from '../api';

export const SessionsPage = ({ sessions, repos }) => {
  const [filter, setFilter] = useState('all');
  const filtered = filter === 'all' ? sessions : sessions.filter(s => s.repo === filter);
  return (
    <>
      <PageHead title="Session log" sub="Every Claude Code session across your repos. Click any row to inspect tool calls, file edits, and the full transcript." />
      <div className="row gap-sm wrap mb-3">
        <span className={'chip' + (filter === 'all' ? ' active' : '')} onClick={() => setFilter('all')}>All ({sessions.length})</span>
        {repos.map(r => (
          <span key={r.id} className={'chip' + (filter === r.id ? ' active' : '')} onClick={() => setFilter(r.id)}>
            <span className={'sb-repo-dot' + (r.isActive ? ' live' : '')} style={{ '--accent': r.accent, width: 6, height: 6 }}></span>
            {r.name}
          </span>
        ))}
      </div>
      <div className="card-frame">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="clock" />{filter === 'all' ? 'All sessions' : repos.find(r => r.id === filter)?.name}</h2>
          <span className="frame-meta">{filtered.length} sessions</span>
        </div>
        <div className="list" style={{ border: 'none', borderRadius: 0 }}>
          <div className="list-head" style={{ gridTemplateColumns: '90px 100px 1.5fr 120px 90px 70px 70px' }}>
            <span>Started</span><span>Repo</span><span>Task</span><span>Agent</span><span>Duration</span><span>Tokens</span><span>Cost</span>
          </div>
          {filtered.map(s => {
            const repo = repos.find(r => r.id === s.repo);
            return (
              <div key={s.id} className="list-row clickable" style={{ gridTemplateColumns: '90px 100px 1.5fr 120px 90px 70px 70px' }}>
                <span className="mono" style={{ fontSize: '.66rem', color: 'var(--muted)' }}>{s.started}</span>
                <span className="row gap-xs"><span className="sb-repo-dot" style={{ '--accent': repo?.accent || 'var(--cyan)', width: 6, height: 6 }}></span>{s.repo}</span>
                <div>
                  <div style={{ color: 'var(--txt-bright)' }}>{s.task}</div>
                  <div style={{ fontSize: '.6rem', color: 'var(--muted)' }}>{s.edits} edits · session #{s.id}</div>
                </div>
                <span className="tp">{s.agent}</span>
                <span>{s.status === 'running' ? <Status kind="running" /> : <span className="mono" style={{ fontSize: '.68rem' }}>{s.duration}</span>}</span>
                <span className="tg">{s.tokens >= 1_000_000 ? (s.tokens / 1_000_000).toFixed(1) + 'M' : (s.tokens / 1000).toFixed(1) + 'k'}</span>
                <span className="tgr">${s.cost.toFixed(2)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
};

export const LivePage = ({ liveEvents, repos }) => (
  <>
    <PageHead title="Live activity feed" sub="Real-time stream of every tool call, agent invocation, skill load and permission check across all tracked repos. Updates as Claude works." actions={<span className="live-pill"><span className="dot"></span>streaming</span>} />
    <div className="grid grid-cols-4 mb-4">
      <Metric label="Active repos" value={repos.filter(r => r.isActive).length} accent="green" />
      <Metric label="Tools/min" value="14.3" accent="cyan" />
      <Metric label="Tokens/min" value="42k" accent="gold" />
      <Metric label="Events buffered" value={liveEvents.length} accent="purple" />
    </div>

    <div className="mb-4">
      <LiveAgents repos={repos} />
    </div>

    <div className="card-frame">
      <div className="card-frame-head">
        <h2 className="section-title"><Icon name="terminal" />Streaming</h2>
        <span className="frame-meta">● {liveEvents.length} events</span>
      </div>
      <LiveTerminal events={liveEvents} height={520} hideHeader={true} />
    </div>
  </>
);

export const AgentsPage = ({ repos, onOpen }) => {
  const all = [];
  repos.forEach(r => r.agents.forEach(a => all.push({ name: a, repo: r.name, kind: 'agent', accent: r.accent })));
  repos.forEach(r => r.skills.forEach(s => all.push({ name: s, repo: r.name, kind: 'skill', accent: r.accent })));
  const [q, setQ] = useState('');
  const filtered = all.filter(x => x.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <PageHead title="Agents & skills" sub="Cross-repo registry. Search to find every place an agent or skill is defined or used." />
      <div className="search-box mb-3" style={{ width: '100%', maxWidth: 480 }}>
        <Icon name="search" size={12} />
        <input placeholder="Search agents and skills…" value={q} onChange={e => setQ(e.target.value)} />
      </div>
      <div className="card-frame">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="bot" />Registry</h2>
          <span className="frame-meta">{filtered.length} of {all.length} entries</span>
        </div>
        <div className="grid grid-auto" style={{ padding: '.85rem' }}>
          {filtered.map((x, i) => (
            <div key={i} className="cd clickable" onClick={() => onOpen && onOpen(x.name, x.kind)}>
              <div className="row between mb-2">
                <div className="row gap-sm">
                  <Icon name={x.kind === 'agent' ? 'bot' : 'sparkles'} size={14} />
                  <h3 className="tb">{x.name}</h3>
                </div>
                <span className={x.kind === 'agent' ? 'bg bg-c' : 'bg bg-p'}>{x.kind}</span>
              </div>
              <div style={{ fontSize: '.66rem', color: 'var(--muted)' }}>
                <span className="sb-repo-dot" style={{ '--accent': x.accent, width: 6, height: 6, display: 'inline-block', marginRight: '.4em' }}></span>
                {x.repo}
              </div>
            </div>
          ))}
          {filtered.length === 0 && <div className="empty">No matches</div>}
        </div>
      </div>
    </>
  );
};

export const PermissionsPanel = ({ scope = 'all repos' }) => {
  const { data: D } = usePermissions();
  const Section = ({ title, items, badge, color }) => (
    <div className="card-frame">
      <div className="card-frame-head">
        <h2 className="section-title" style={{ color }}>
          <Icon name={badge === 'allow' ? 'check' : badge === 'deny' ? 'x' : 'eye'} size={13} />
          {title}
        </h2>
        <span className={'bg bg-' + (badge === 'allow' ? 'gr' : badge === 'deny' ? 'r' : 'g')}>{items.length}</span>
      </div>
      <div className="col gap-xs" style={{ padding: '.6rem .7rem' }}>
        {items.map((p, i) => (
          <div key={i} style={{ padding: '.4rem .65rem', display: 'flex', alignItems: 'center', gap: '.5rem', background: 'var(--code-bg)', border: '1px solid var(--brd2)', borderRadius: 5 }}>
            <Icon name={badge === 'allow' ? 'check' : badge === 'deny' ? 'x' : 'eye'} size={11} style={{ color }} />
            <span className="mono" style={{ fontSize: '.7rem' }}>{p}</span>
          </div>
        ))}
      </div>
    </div>
  );
  return (
    <>
      <div className="row gap-sm mb-3">
        <span className="lbl">Scope:</span><span className="bg bg-c">{scope}</span>
      </div>
      <div className="grid grid-cols-3">
        <Section title="Allow" items={D.allow} badge="allow" color="var(--green)" />
        <Section title="Ask" items={D.ask} badge="ask" color="var(--gold)" />
        <Section title="Deny" items={D.deny} badge="deny" color="var(--rose)" />
      </div>
    </>
  );
};

export const PluginsPanel = ({ repo }) => {
  const pluginInfo = {
    linear: { desc: 'Linear MCP — fetch tickets, projects, comments', accent: 'p' },
    slack: { desc: 'Slack — post updates and read threads', accent: 'g' },
    sentry: { desc: 'Sentry — pull errors and stack traces', accent: 'ro' },
    figma: { desc: 'Figma — extract design context', accent: 'p' },
    greptile: { desc: 'Greptile — codebase semantic search', accent: 't' },
    'pr-review-toolkit': { desc: 'PR Review Toolkit — automated review', accent: 'c' },
  };
  const mcpInfo = {
    filesystem: { desc: 'Local filesystem read/write/search' },
    'sequential-thinking': { desc: 'Multi-step reasoning helper' },
    linear: { desc: 'Linear API server' },
    'linear-server': { desc: 'Linear API (alternate)' },
    github: { desc: 'GitHub API access' },
    playwright: { desc: 'Browser automation' },
    figma: { desc: 'Figma design context' },
    'code-review-graph': { desc: 'Code review graph + impact analysis' },
  };
  return (
    <>
      <div className="card-frame">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="pkg" />Plugins enabled</h2>
          <span className="frame-meta">{(repo?.plugins || []).length} active</span>
        </div>
        <div className="grid grid-cols-2" style={{ padding: '.85rem' }}>
          {(repo?.plugins || []).map(p => {
            const info = pluginInfo[p] || { desc: 'Plugin', accent: 'c' };
            return (
              <div key={p} className="cd">
                <div className="row between mb-2">
                  <div className="row gap-sm"><Icon name="pkg" size={14} /><h3 className="tb">{p}</h3></div>
                  <span className={'bg bg-' + info.accent}>plugin</span>
                </div>
                <p style={{ fontSize: '.72rem', color: 'var(--txt)' }}>{info.desc}</p>
                <div className="mono mt-2" style={{ fontSize: '.62rem', color: 'var(--muted)' }}>{p}@claude-plugins-official</div>
              </div>
            );
          })}
        </div>
      </div>
      <div className="card-frame mt-4">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="cpu" />MCP servers</h2>
          <span className="frame-meta">{(repo?.mcp || []).length} connected</span>
        </div>
        <div className="grid grid-cols-2" style={{ padding: '.85rem' }}>
          {(repo?.mcp || []).map(m => {
            const info = mcpInfo[m] || { desc: 'MCP server' };
            return (
              <div key={m} className="cd">
                <div className="row between mb-2">
                  <div className="row gap-sm"><Icon name="cpu" size={14} /><h3 className="tb">{m}</h3></div>
                  <span className="bg bg-c">mcp</span>
                </div>
                <p style={{ fontSize: '.72rem', color: 'var(--txt)' }}>{info.desc}</p>
                <div className="row gap-xs mt-2">
                  <span className="status status-running"><span className="dot"></span>connected</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
};
