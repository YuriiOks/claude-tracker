import { useState } from 'react';
import Icon from '../icons';
import { Metric, Status, Tabs, PageHead } from './Common';
import LiveTerminal from './LiveTerminal';
import { PermissionsPanel, PluginsPanel } from './Pages';
import { AGENT_META } from '../data';

const RepoOverview = ({ repo, repoSessions, repoEvents, onOpen }) => (
  <div className="split">
    <div>
      <h2 className="section-title mb-3"><Icon name="terminal" />Recent activity</h2>
      <LiveTerminal events={repoEvents.slice(-18)} height={300} />

      <h2 className="section-title mt-5 mb-3"><Icon name="clock" />Sessions in this repo</h2>
      <div className="list">
        {repoSessions.length > 0 ? repoSessions.map(s => (
          <div key={s.id} className="list-row" style={{ gridTemplateColumns: '60px 1fr 100px 70px 60px' }}>
            <span className="mono" style={{ fontSize: '.62rem', color: 'var(--muted)' }}>{s.started}</span>
            <div>
              <div style={{ fontSize: '.74rem', color: 'var(--txt-bright)' }}>{s.task}</div>
              <div style={{ fontSize: '.6rem', color: 'var(--muted)' }}><span className="tp">{s.agent}</span> · {s.duration}</div>
            </div>
            <Status kind={s.status} />
            <span className="tg" style={{ fontSize: '.7rem' }}>${s.cost.toFixed(2)}</span>
            <span className="bg bg-m">{s.edits} edits</span>
          </div>
        )) : <div className="empty">No sessions yet</div>}
      </div>
    </div>

    <div>
      <h2 className="section-title mb-3"><Icon name="layers" />.claude/ structure</h2>
      <div className="cd" style={{ padding: '.85rem 1rem' }}>
        <div className="mono" style={{ fontSize: '.7rem', lineHeight: 1.85, color: 'var(--txt)' }}>
          <div><span className="tc">📁</span> .claude/</div>
          <div style={{ paddingLeft: '1rem' }}><span className="to">📄</span> settings.json</div>
          <div style={{ paddingLeft: '1rem' }}><span className="to">📄</span> settings.local.json</div>
          <div style={{ paddingLeft: '1rem' }}>📁 agents/ <span className="tm">({repo.agents.length})</span></div>
          {repo.agents.slice(0, 4).map(a => (
            <div key={a} style={{ paddingLeft: '2rem', cursor: 'pointer' }} onClick={() => onOpen && onOpen(a, 'agent')}>
              <span className="tg">→</span> {a}.md
            </div>
          ))}
          {repo.agents.length > 4 && <div style={{ paddingLeft: '2rem', color: 'var(--muted)' }}>… +{repo.agents.length - 4} more</div>}
          <div style={{ paddingLeft: '1rem' }}>📁 skills/ <span className="tm">({repo.skills.length})</span></div>
          {repo.skills.slice(0, 3).map(s => (
            <div key={s} style={{ paddingLeft: '2rem' }}><span className="tp">→</span> {s}/SKILL.md</div>
          ))}
          <div style={{ paddingLeft: '1rem' }}>📁 commands/ <span className="tm">({repo.commands.length})</span></div>
          {repo.commands.slice(0, 3).map(c => (
            <div key={c} style={{ paddingLeft: '2rem' }}><span className="to">→</span> {c.replace('/', '')}.md</div>
          ))}
          {(repo.rules || []).length > 0 && <div style={{ paddingLeft: '1rem' }}>📁 rules/ <span className="tm">({repo.rules.length})</span></div>}
        </div>
      </div>

      <h2 className="section-title mt-4 mb-3"><Icon name="plug" />Plugins enabled</h2>
      <div className="tag-row">
        {(repo.plugins || []).map(p => <span key={p} className="bg bg-p"><Icon name="pkg" size={10} />{p}</span>)}
      </div>

      <h2 className="section-title mt-4 mb-3"><Icon name="cpu" />MCP servers</h2>
      <div className="tag-row">
        {(repo.mcp || []).map(m => <span key={m} className="bg bg-c"><Icon name="cpu" size={10} />{m}</span>)}
      </div>
    </div>
  </div>
);

const RepoAgents = ({ repo, onOpen }) => (
  <div className="grid grid-auto">
    {repo.agents.map(a => {
      const meta = AGENT_META[a];
      return (
        <div key={a} className="cd clickable" onClick={() => onOpen && onOpen(a, 'agent')}>
          <div className="row between mb-2">
            <div className="row gap-sm">
              <Icon name="bot" size={16} />
              <h3 className="tb">{a}</h3>
            </div>
            <span className="bg bg-c">agent</span>
          </div>
          <p style={{ fontSize: '.72rem', color: 'var(--txt)', marginBottom: '.7rem' }}>
            {meta?.role || 'Specialist agent for this repository.'}
          </p>
          <div className="row wrap gap-xs mb-2">
            {(meta?.tools || ['Read', 'Edit', 'Bash']).map(t => <span key={t} className="chip">{t}</span>)}
          </div>
          {meta && (
            <div className="row between" style={{ fontSize: '.62rem', color: 'var(--muted)' }}>
              <span><span className="tc">{meta.callsToday}</span> calls today</span>
              <span><span className="tg">{(meta.avgTokens / 1000).toFixed(1)}k</span> avg tokens</span>
              {meta.delegates.length > 0 && <span><span className="tp">{meta.delegates.length}</span> delegates</span>}
            </div>
          )}
        </div>
      );
    })}
  </div>
);

const RepoSkills = ({ repo }) => (
  <div className="grid grid-auto">
    {repo.skills.map(s => (
      <div key={s} className="cd clickable">
        <div className="row between mb-2">
          <div className="row gap-sm"><Icon name="sparkles" size={16} /><h3 className="tb">{s}</h3></div>
          <span className="bg bg-p">skill</span>
        </div>
        <p style={{ fontSize: '.72rem', color: 'var(--txt)' }}>SKILL.md defines reusable workflow knowledge that Claude loads when working on relevant files.</p>
        <div className="divider"></div>
        <div className="mono" style={{ fontSize: '.62rem', color: 'var(--muted)' }}>.claude/skills/{s}/SKILL.md</div>
      </div>
    ))}
  </div>
);

const RepoCommands = ({ repo }) => (
  <div className="grid grid-cols-2">
    {repo.commands.map(c => (
      <div key={c} className="cd">
        <div className="row between mb-2">
          <div className="row gap-sm"><Icon name="terminal" size={14} /><h3 className="tb mono">{c}</h3></div>
          <span className="bg bg-o">command</span>
        </div>
        <div className="code">
          <span className="cmt"># Slash command — invoked from Claude Code</span><br />
          <span className="kw">$</span> <span className="fn">{c}</span> <span className="vr">$ARGUMENTS</span>
        </div>
      </div>
    ))}
  </div>
);

const RepoRules = ({ repo }) => (
  <div className="col gap-sm">
    {(repo.rules || []).map(r => (
      <div key={r} className="cd">
        <div className="row between mb-2">
          <div className="row gap-sm"><Icon name="book" size={14} /><h3 className="tb">{r}</h3></div>
          <span className="bg bg-t">rule</span>
        </div>
        <div className="mono" style={{ fontSize: '.66rem', color: 'var(--muted)' }}>
          .claude/rules/{r}.md · auto-applies based on file path globs
        </div>
      </div>
    ))}
    {(repo.rules || []).length === 0 && <div className="empty">No rules defined</div>}
  </div>
);

const RepoDetail = ({ repo, sessions, liveEvents, onOpen }) => {
  const [tab, setTab] = useState('overview');
  const isGlobal = repo.id === 'global';
  const repoEvents = liveEvents.filter(e => e.repo === repo.id || (isGlobal && true));
  const repoSessions = sessions.filter(s => s.repo === repo.id);

  return (
    <>
      <PageHead
        title={repo.name}
        accent={repo.accent}
        sub={<>
          <span className="mono" style={{ color: 'var(--muted)' }}>{repo.path}</span>
          {!isGlobal && <> · branch <span className="mono tg">{repo.branch}</span></>}
          <br />{repo.description}
        </>}
        actions={<>
          {!isGlobal && (repo.isActive
            ? <span className="live-pill"><span className="dot"></span>session live</span>
            : <Status kind="idle" />)}
          <button className="btn"><Icon name="eye" size={12} />Open in editor</button>
          <button className="btn primary"><Icon name="terminal" size={12} />Tail session</button>
        </>}
      />

      {!isGlobal && (
        <div className="grid grid-cols-4 mb-5 mt-4">
          <Metric label="Sessions today" value={repo.stats.sessionsToday} accent="cyan" />
          <Metric label="Tokens this week" value={(repo.stats.tokensWeek / 1e6).toFixed(2)} unit="M" accent="gold" />
          <Metric label="Cost this week" value={`$${repo.stats.costWeek.toFixed(2)}`} accent="green" />
          <Metric label="Avg session" value={repo.stats.avgSession} accent="purple" />
        </div>
      )}

      <Tabs
        items={[
          { id: 'overview', label: 'Overview', icon: 'layers' },
          { id: 'agents', label: 'Agents', icon: 'bot', count: repo.agents.length },
          { id: 'skills', label: 'Skills', icon: 'sparkles', count: repo.skills.length },
          { id: 'commands', label: 'Commands', icon: 'terminal', count: repo.commands.length },
          { id: 'rules', label: 'Rules', icon: 'book', count: (repo.rules || []).length },
          { id: 'permissions', label: 'Permissions', icon: 'shield' },
          { id: 'plugins', label: 'Plugins / MCP', icon: 'plug' },
        ]}
        value={tab}
        onChange={setTab}
      />

      {tab === 'overview' && <RepoOverview repo={repo} repoSessions={repoSessions} repoEvents={repoEvents} onOpen={onOpen} />}
      {tab === 'agents' && <RepoAgents repo={repo} onOpen={onOpen} />}
      {tab === 'skills' && <RepoSkills repo={repo} />}
      {tab === 'commands' && <RepoCommands repo={repo} />}
      {tab === 'rules' && <RepoRules repo={repo} />}
      {tab === 'permissions' && <PermissionsPanel scope={repo.name} />}
      {tab === 'plugins' && <PluginsPanel repo={repo} />}
    </>
  );
};

export default RepoDetail;
