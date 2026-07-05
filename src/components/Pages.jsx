import { useState } from 'react';
import Icon from '../icons';
import { Metric, Status, PageHead } from './Common';
import LiveTerminal from './LiveTerminal';
import LiveAgents from './LiveAgents';
import { usePermissions, useGlobal } from "../api";
import PermissionsKanban from "./PermissionsKanban";
import { PLUGIN_REGISTRY } from '../data';

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
          {filtered.length === 0 && <div className="empty">No sessions recorded yet.</div>}
        </div>
      </div>
    </>
  );
};

export const LivePage = ({ liveEvents, repos, onOpen, repoFilter = null, liveAgents }) => {
  // F9: compute live metrics from the actual event stream instead of fake constants.
  // Events carry `t` as a delta in seconds from now (negative = past).
  const events = repoFilter ? liveEvents.filter(e => e.repo === repoFilter) : liveEvents;
  const filteredRepos = repoFilter ? repos.filter(r => r.id === repoFilter) : repos;
  const last60 = events.filter(e => e.t >= -60);
  const eventsPerMin = last60.length;
  const toolsPerMin = last60.filter(e => e.kind === 'tool' || e.kind === 'command').length;
  return (
  <>
    <PageHead title="Live activity feed" sub="Real-time stream of every tool call, agent invocation, skill load and permission check across all tracked repos. Updates as Claude works." actions={<span className="live-pill"><span className="dot"></span>streaming</span>} />
    {repoFilter && (
      <div className="row gap-sm mb-3" style={{ fontSize: '.75rem', color: 'var(--muted)' }}>
        <span className="status status-running"><span className="dot"></span>Filtered to: <strong style={{ color: 'var(--cyan)' }}>{repoFilter}</strong></span>
      </div>
    )}
    <div className="grid grid-cols-4 mb-4">
      <Metric label="Active repos" value={filteredRepos.filter(r => r.isActive).length} accent="green" />
      <Metric label="Tools / min" value={toolsPerMin} accent="cyan" />
      <Metric label="Events / min" value={eventsPerMin} accent="gold" />
      <Metric label="Events buffered" value={events.length} accent="purple" />
    </div>

    <div className="mb-4">
      <LiveAgents repos={filteredRepos} onOpen={onOpen} agents={liveAgents} />
    </div>

    <div className="card-frame">
      <div className="card-frame-head">
        <h2 className="section-title"><Icon name="terminal" />Streaming</h2>
        <span className="frame-meta">● {events.length} events</span>
      </div>
      <LiveTerminal events={events} height={520} hideHeader={true} />
    </div>
  </>
  );
};

export const AgentsPage = ({ repos, onOpen }) => {
  const all = [];
  repos.forEach(r => r.agents.forEach(a => all.push({ name: a, repo: r.name, repoId: r.id, kind: 'agent', accent: r.accent })));
  repos.forEach(r => r.skills.forEach(s => all.push({ name: s, repo: r.name, repoId: r.id, kind: 'skill', accent: r.accent })));
  const [q, setQ] = useState('');
  const [repoFilter, setRepoFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const filtered = all.filter(x =>
    (repoFilter === 'all' || x.repoId === repoFilter) &&
    (typeFilter === 'all' || x.kind === typeFilter) &&
    x.name.toLowerCase().includes(q.toLowerCase())
  );
  return (
    <>
      <PageHead title="Agents & skills" sub="Cross-repo registry. Search to find every place an agent or skill is defined or used." />
      <div className="search-box mb-3" style={{ width: '100%', maxWidth: 480 }}>
        <Icon name="search" size={12} />
        <input placeholder="Search agents and skills…" value={q} onChange={e => setQ(e.target.value)} />
      </div>
      <div className="row gap-xs mb-3 flex-wrap">
        <span className={'chip' + (repoFilter === 'all' ? ' active' : '')} onClick={() => setRepoFilter('all')}>All repos</span>
        {repos.map(r => (
          <span key={r.id} className={'chip' + (repoFilter === r.id ? ' active' : '')} onClick={() => setRepoFilter(r.id)}>
            <span className="sb-repo-dot" style={{ '--accent': r.accent, width: 6, height: 6 }}></span>
            {r.name}
          </span>
        ))}
      </div>
      <div className="row gap-xs mb-3 flex-wrap">
        <span className={'chip' + (typeFilter === 'all' ? ' active' : '')} onClick={() => setTypeFilter('all')}>All</span>
        <span className={'chip bg-c' + (typeFilter === 'agent' ? ' active' : '')} onClick={() => setTypeFilter('agent')}>Agents</span>
        <span className={'chip bg-p' + (typeFilter === 'skill' ? ' active' : '')} onClick={() => setTypeFilter('skill')}>Skills</span>
      </div>
      <div className="card-frame">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="bot" />Registry</h2>
          <span className="frame-meta">{filtered.length} of {all.length} entries</span>
        </div>
        <div className="grid grid-auto" style={{ padding: '.85rem' }}>
          {filtered.map((x) => (
            <div key={x.kind + '-' + x.name} className="cd clickable" onClick={() => onOpen && onOpen(x.name, x.kind, x.repoId)}>
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

// Read-only aggregated view (cross-repo).
export const PermissionsPanelReadOnly = ({ scope = "all repos" }) => {
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

// Default PermissionsPanel — the interactive kanban editor. Tabs in
// RepoDetail call this; RepoDetail passes the repo id as `scope` so
// the editor lands on that repo's .claude/settings*.json.
export const PermissionsPanel = ({ scope }) => {
  const initial = (scope && scope !== "all repos") ? scope : "global";
  return <PermissionsKanban defaultScope={initial} />;
};

export const PluginsPanel = ({ repo, onOpen }) => {
  const pluginInfo = PLUGIN_REGISTRY;
  // Per-repo plugins/MCP are usually empty in real installs — Claude Code
  // stores plugins globally in ~/.claude/plugins/installed_plugins.json and
  // MCP servers in ~/.claude.json, not in <repo>/.claude/settings.json. Fall
  // back to GLOBAL so the user sees what is actually available in this repo.
  const { data: G } = useGlobal();
  const repoPlugins = repo?.plugins || [];
  const repoMcp = repo?.mcp || [];
  const plugins = repoPlugins.length > 0 ? repoPlugins : (G?.plugins || []);
  const mcp = repoMcp.length > 0 ? repoMcp : (G?.mcp || []);
  const pluginsFromGlobal = repoPlugins.length === 0 && plugins.length > 0;
  const mcpFromGlobal = repoMcp.length === 0 && mcp.length > 0;
  return (
    <>
      <div className="card-frame">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="pkg" />Plugins enabled</h2>
          <span className="frame-meta">{plugins.length} active{pluginsFromGlobal ? " (global)" : ""}</span>
        </div>
        <div className="grid grid-cols-2" style={{ padding: '.85rem' }}>
          {plugins.map(p => {
            // Plugin names from the backend look like "name@marketplace"
            // (e.g. "Notion@claude-plugins-official"). Split for display so
            // the title stays clean and the meta line shows the source —
            // without this the hardcoded suffix below would duplicate it.
            const [name, source = 'local'] = String(p).split('@');
            const info = pluginInfo[name] || pluginInfo[p] || { desc: 'Installed plugin', accent: 'c' };
            return (
              <div key={p} className="cd clickable" onClick={() => onOpen && onOpen(name, 'plugin', repo?.id)}>
                <div className="row between mb-2">
                  <div className="row gap-sm"><Icon name="pkg" size={14} /><h3 className="tb">{name}</h3></div>
                  <span className={'bg bg-' + info.accent}>plugin</span>
                </div>
                <div className="mono" style={{ fontSize: '.62rem', color: 'var(--muted)' }}>{source}</div>
              </div>
            );
          })}
          {plugins.length === 0 && <div className="empty">No plugins enabled.</div>}
        </div>
      </div>
      <div className="card-frame mt-4">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="cpu" />MCP servers</h2>
          <span className="frame-meta">{mcp.length} connected{mcpFromGlobal ? " (global)" : ""}</span>
        </div>
        <div className="grid grid-cols-2" style={{ padding: '.85rem' }}>
          {mcp.map(m => {
            return (
              <div key={m} className="cd clickable" onClick={() => onOpen && onOpen(m, 'mcp', repo?.id)}>
                <div className="row between mb-2">
                  <div className="row gap-sm"><Icon name="cpu" size={14} /><h3 className="tb">{m}</h3></div>
                  <span className="bg bg-p">mcp</span>
                </div>
                <span className="status status-running" style={{ fontSize: '.62rem' }}><span className="dot"></span>connected</span>
              </div>
            );
          })}
          {mcp.length === 0 && <div className="empty">No MCP servers connected.</div>}
        </div>
      </div>
    </>
  );
};
