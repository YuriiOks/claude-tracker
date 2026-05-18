import { useState } from 'react';
import Icon from '../icons';
import { Metric, Status, Tabs, PageHead } from './Common';
import MarkdownPanel from './MarkdownPanel';
import { useRepoHtmlArtifacts } from '../api';
import LiveTerminal from './LiveTerminal';
import { PermissionsPanel, PluginsPanel } from './Pages';
import { useAgents } from '../api';

const HtmlArtifacts = ({ repo }) => {
  const { data: artifacts } = useRepoHtmlArtifacts(repo.id);
  const [active, setActive] = useState(null);
  if (!artifacts || artifacts.length === 0) return null;
  return (
    <div className="mt-4">
      <h2 className="section-title mb-3"><Icon name="file" />Generated HTML artifacts</h2>
      <div className="row gap-sm wrap mb-3">
        {artifacts.map(a => (
          <button
            key={a.path}
            className={'chip' + (active === a.path ? ' active' : '')}
            onClick={() => setActive(active === a.path ? null : a.path)}
            title={`${a.path} · ${(a.size / 1024).toFixed(1)} KB`}
          >
            <Icon name="eye" size={10} />{a.name}
          </button>
        ))}
      </div>
      {active && (
        <MarkdownPanel
          key={active}
          repoId={repo.id}
          relPath={active}
          filePath={active}
          defaultMode="html"
          emptyMessage="Artifact not readable"
        />
      )}
    </div>
  );
};

const ClaudeTree = ({ repo, onOpen }) => {
  // Each folder starts collapsed; clicking the row toggles. Single-shot file
  // viewer for settings*.json (the only leaves that aren't agents/skills/commands/rules).
  const [open, setOpen] = useState({ agents: false, skills: false, commands: false, rules: false });
  const [viewFile, setViewFile] = useState(null);
  const toggle = (k) => setOpen(o => ({ ...o, [k]: !o[k] }));
  const folder = (k, label, items, kind, accent) => (
    <>
      <div className="ct-row ct-folder" onClick={() => toggle(k)}>
        <span className={'ct-chev' + (open[k] ? ' ct-chev-open' : '')}><Icon name="chevronRight" size={9} /></span>
        <span className="ct-emoji">📁</span>
        <span>{label}/</span>
        <span className="tm ct-count">({items.length})</span>
      </div>
      {open[k] && items.map(name => {
        const cleaned = kind === 'command' ? name.replace(/^\//, '') : name;
        const suffix = kind === 'skill' ? '/SKILL.md' : '.md';
        const display = kind === 'command' ? '/' + cleaned + '.md' : cleaned + suffix;
        return (
          <div key={name} className="ct-row ct-leaf" onClick={() => onOpen && onOpen(cleaned, kind)}>
            <span className={'ct-arrow ' + accent}>→</span>
            <span>{display}</span>
          </div>
        );
      })}
      {open[k] && items.length === 0 && (
        <div className="ct-row ct-empty"><span className="ct-arrow">·</span><span>empty</span></div>
      )}
    </>
  );
  return (
    <>
      <div className="cd ct-card">
        <div className="mono ct-tree">
          <div className="ct-row ct-root"><span className="ct-emoji tc">📁</span> .claude/</div>
          <div className={'ct-row ct-file' + (viewFile === 'settings.json' ? ' ct-file-active' : '')} onClick={() => setViewFile(viewFile === 'settings.json' ? null : 'settings.json')}>
            <span className="ct-emoji to">📄</span> settings.json
          </div>
          <div className={'ct-row ct-file' + (viewFile === 'settings.local.json' ? ' ct-file-active' : '')} onClick={() => setViewFile(viewFile === 'settings.local.json' ? null : 'settings.local.json')}>
            <span className="ct-emoji to">📄</span> settings.local.json
          </div>
          {folder('agents', 'agents', repo.agents || [], 'agent', 'tg')}
          {folder('skills', 'skills', repo.skills || [], 'skill', 'tp')}
          {folder('commands', 'commands', repo.commands || [], 'command', 'to')}
          {folder('rules', 'rules', repo.rules || [], 'rule', 'tt')}
        </div>
      </div>
      {viewFile && (
        <div className="mt-3">
          <MarkdownPanel
            key={viewFile}
            repoId={repo.id}
            relPath={'.claude/' + viewFile}
            filePath={'.claude/' + viewFile}
            defaultMode="code"
            emptyMessage={'File not found: .claude/' + viewFile}
          />
        </div>
      )}
    </>
  );
};

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
      <ClaudeTree repo={repo} onOpen={onOpen} />

      <h2 className="section-title mt-4 mb-3"><Icon name="plug" />Plugins enabled</h2>
      <div className="tag-row">
        {(repo.plugins || []).map(p => <span key={p} className="bg bg-p"><Icon name="pkg" size={10} />{p}</span>)}
      </div>

      <h2 className="section-title mt-4 mb-3"><Icon name="cpu" />MCP servers</h2>
      <div className="tag-row">
        {(repo.mcp || []).map(m => <span key={m} className="bg bg-c"><Icon name="cpu" size={10} />{m}</span>)}
      </div>

      <HtmlArtifacts repo={repo} />
    </div>
  </div>
);

const RepoAgents = ({ repo, onOpen }) => {
  const { data: AGENT_META } = useAgents();
  return (
  <div className="grid grid-auto">
    {repo.agents.map(a => {
      const meta = AGENT_META?.[a];
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
};

const RepoSkills = ({ repo, onOpen }) => (
  <div className="grid grid-auto">
    {repo.skills.map(s => (
      <div key={s} className="cd clickable" onClick={() => onOpen && onOpen(s, 'skill')}>
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

const RepoCommands = ({ repo, onOpen }) => (
  <div className="grid grid-cols-2">
    {repo.commands.map(c => (
      <div key={c} className="cd clickable" onClick={() => onOpen && onOpen(c.replace(/^\//, ''), 'command')}>
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

const RepoRules = ({ repo, onOpen }) => (
  <div className="col gap-sm">
    {(repo.rules || []).map(r => (
      <div key={r} className="cd clickable" onClick={() => onOpen && onOpen(r, 'rule')}>
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

const RepoDetail = ({ repo, sessions, liveEvents, onOpen, tab = 'overview', onTabChange, setRoute }) => {
  const setTab = onTabChange || (() => {});
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
          <button
            className="btn"
            title="Copy the repo path to clipboard so you can open it in your editor"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(repo.path);
              } catch {
                window.prompt('Repo path:', repo.path);
              }
            }}
          ><Icon name="eye" size={12} />Copy path</button>
          <button
            className="btn primary"
            title="Open the live activity feed (filtered to all repos for now)"
            onClick={() => setRoute && setRoute({ page: 'live' })}
          ><Icon name="terminal" size={12} />Tail session</button>
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
      {tab === 'skills' && <RepoSkills repo={repo} onOpen={onOpen} />}
      {tab === 'commands' && <RepoCommands repo={repo} onOpen={onOpen} />}
      {tab === 'rules' && <RepoRules repo={repo} onOpen={onOpen} />}
      {tab === 'permissions' && <PermissionsPanel scope={repo.name} />}
      {tab === 'plugins' && <PluginsPanel repo={repo} />}
    </>
  );
};

export default RepoDetail;
