import { useMemo, useState } from 'react';
import Icon from '../icons';
import { Metric, Status, PageHead } from './Common';
import { useAgents, useRepoHtmlArtifacts, useSessions } from '../api';
import MarkdownPanel from './MarkdownPanel';

// Templates section — when a skill has a `templates/` subdir (e.g. html-docs),
// list the .html templates so the user can preview them inline.
const SkillTemplatesPanel = ({ repoId, skillName }) => {
  const dir = `.claude/skills/${skillName}/templates`;
  const { data: templates } = useRepoHtmlArtifacts(repoId, dir);
  const [active, setActive] = useState(null);
  if (!templates || templates.length === 0) return null;
  return (
    <div className="mt-4">
      <h2 className="section-title mb-3"><Icon name="layers" />Templates ({templates.length})</h2>
      <div className="row gap-sm wrap mb-3">
        {templates.map(t => (
          <button
            key={t.path}
            className={'chip' + (active === t.path ? ' active' : '')}
            onClick={() => setActive(active === t.path ? null : t.path)}
            title={`${t.path} · ${(t.size / 1024).toFixed(1)} KB`}
          >
            <Icon name="eye" size={10} />{t.name}
          </button>
        ))}
      </div>
      {active && (
        <MarkdownPanel
          key={active}
          repoId={repoId}
          relPath={active}
          filePath={active}
          defaultMode="html"
          hideSourceToggle
          emptyMessage="Template not readable"
        />
      )}
    </div>
  );
};

// Minimal detail view for commands and rules (no metadata schema yet).
const SimpleItemDetail = ({ name, kind, repo, onBack }) => {
  const isCmd = kind === 'command';
  const fileLabel = isCmd
    ? `.claude/commands/${name}.md`
    : `.claude/rules/${name}.md`;
  const accent = isCmd ? 'var(--green)' : 'var(--gold)';
  const badge = isCmd ? 'bg-o' : 'bg-t';
  const iconName = isCmd ? 'terminal' : 'book';
  return (
    <>
      <button className="page-back" onClick={onBack}><Icon name="x" size={11} /><span>Back</span></button>
      <PageHead
        title={isCmd ? `/${name}` : name}
        accent={accent}
        sub={isCmd
          ? 'Slash command — invoked from Claude Code with `/' + name + '` followed by arguments.'
          : 'Rule — auto-applied based on file path globs declared in the rule frontmatter.'}
        actions={<>
          <span className={'bg ' + badge}>
            <Icon name={iconName} size={10} />{kind}
          </span>
          {repo && <span className="bg bg-m">{repo.name}</span>}
        </>}
      />
      <div style={{ marginTop: '1rem' }}>
        <MarkdownPanel
          repoId={repo?.id}
          relPath={fileLabel}
          filePath={fileLabel}
          emptyMessage={isCmd ? 'Command file not found in repo.' : 'Rule file not found in repo.'}
        />
      </div>
    </>
  );
};

// Format "2m ago" / "1h ago" / "3d ago" from an ISO timestamp.
function timeAgo(iso) {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (!t) return '—';
  const dt = Math.max(0, (Date.now() - t) / 1000);
  if (dt < 60) return `${Math.round(dt)}s ago`;
  if (dt < 3600) return `${Math.round(dt / 60)}m ago`;
  if (dt < 86400) return `${Math.round(dt / 3600)}h ago`;
  return `${Math.round(dt / 86400)}d ago`;
}

const AgentDetail = ({ name, kind, repos, repoId, onBack, setRoute }) => {
  // Hooks must run unconditionally — call them ALL first, then dispatch on kind.
  const { data: AGENT_META } = useAgents();
  const { data: sessions } = useSessions(500);

  // Resolve repo first so the memos below can reference it. command/rule
  // kinds use a slightly different fallback chain but we share resolution.
  const repo = (repoId && (repos || []).find(r => r.id === repoId))
    || (repos || []).find(r => r.id === "global")
    || (repos || [])[0];

  const repoIdFinal = repo?.id ?? null;

  // Derive real "Recent invocations" from sessions filtered by agent name.
  const invocations = useMemo(() => {
    const all = (sessions || []).filter(s => s && s.agent === name);
    const scoped = repoIdFinal ? all.filter(s => s.repo === repoIdFinal) : all;
    return scoped.slice(0, 8);
  }, [sessions, name, repoIdFinal]);

  const todayCount = useMemo(() => {
    if (!sessions) return null;
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const cutoff = today.getTime();
    return sessions.filter(s => {
      if (!s || s.agent !== name) return false;
      const t = s.started ? new Date(s.started).getTime() : 0;
      return t >= cutoff;
    }).length;
  }, [sessions, name]);

  const weekCount = useMemo(() => {
    if (!sessions) return null;
    const cutoff = Date.now() - 7 * 86400 * 1000;
    return sessions.filter(s => {
      if (!s || s.agent !== name) return false;
      const t = s.started ? new Date(s.started).getTime() : 0;
      return t >= cutoff;
    }).length;
  }, [sessions, name]);

  // Now safe to dispatch on kind — every hook has run.
  if (kind === "command" || kind === "rule") {
    return <SimpleItemDetail name={name} kind={kind} repo={repo} onBack={onBack} />;
  }

  // Real metadata if backend has it; otherwise an honest empty shell.
  const meta = (AGENT_META && AGENT_META[name]) || {
    role: kind === "skill"
      ? "Skill — encapsulated workflow knowledge that Claude loads when relevant files are touched."
      : "Specialist agent — defined in .claude/agents/" + name + ".md.",
    repo: repoId || null,
    tools: ["Read", "Edit", "Bash", "Grep"],
    callsToday: null,
    avgTokens: null,
    delegates: [],
  };
  const isAgent = kind === "agent";

  // No reliable token data on sessions yet — display "—" when missing.
  const avgTokensK = meta.avgTokens ? (meta.avgTokens / 1000).toFixed(1) : null;

  return (
    <>
      <button className="page-back" onClick={onBack}><Icon name="x" size={11} /><span>Back</span></button>

      <PageHead
        title={name}
        accent={isAgent ? 'var(--cyan)' : 'var(--purple)'}
        sub={meta.role}
        actions={<>
          <span className={isAgent ? 'bg bg-c' : 'bg bg-p'}>
            <Icon name={isAgent ? 'bot' : 'sparkles'} size={10} />{kind}
          </span>
          {repo && <span className="bg bg-m">{repo.name}</span>}
        </>}
      />

      <div className="grid grid-cols-4 mb-4">
        <Metric label="Calls today" value={todayCount == null ? '—' : todayCount} accent="cyan" />
        <Metric label="Avg tokens" value={avgTokensK == null ? '—' : avgTokensK} unit={avgTokensK == null ? '' : 'k'} accent="gold" />
        <Metric label="Calls this week" value={weekCount == null ? '—' : weekCount} accent="purple" />
        <Metric label="Invocations" value={invocations.length} accent="green" />
      </div>

      <div className="split">
        <div>
          <h2 className="section-title mb-3"><Icon name="file" />Definition</h2>
          <MarkdownPanel
            repoId={repo?.id}
            relPath={'.claude/' + (isAgent ? 'agents' : 'skills') + '/' + name + (isAgent ? '.md' : '/SKILL.md')}
            filePath={'.claude/' + (isAgent ? 'agents' : 'skills') + '/' + name + (isAgent ? '.md' : '/SKILL.md')}
            emptyMessage={isAgent ? 'Agent file not found in this repo.' : 'Skill file not found in this repo.'}
          />

          {!isAgent && <SkillTemplatesPanel repoId={repo?.id} skillName={name} />}

          {isAgent && meta.delegates && meta.delegates.length > 0 && (
            <>
              <h2 className="section-title mt-4 mb-3"><Icon name="bot" />Delegates to</h2>
              <div className="row gap-sm wrap">
                {meta.delegates.map(d => <span key={d} className="chip"><Icon name="bot" size={10} />{d}</span>)}
              </div>
            </>
          )}
        </div>

        <div>
          <h2 className="section-title mb-3"><Icon name="zap" />Recent invocations</h2>
          <div className="list">
            {invocations.length === 0 && <div className="empty">No invocations yet.</div>}
            {invocations.map((inv) => (
              <div key={inv.id} className="list-row" style={{ gridTemplateColumns: '60px 1fr 80px 60px' }}>
                <span className="mono" style={{ fontSize: '.62rem', color: 'var(--muted)' }}>{timeAgo(inv.started)}</span>
                <div>
                  <div style={{ fontSize: '.72rem', color: 'var(--txt-bright)' }}>{inv.task}</div>
                  <div style={{ fontSize: '.6rem', color: 'var(--muted)' }}>{inv.repo}</div>
                </div>
                <Status kind={inv.status} />
                <span className="tg" style={{ fontSize: '.7rem' }}>${(inv.cost || 0).toFixed(2)}</span>
              </div>
            ))}
          </div>

          {isAgent && (
            <>
              <h2 className="section-title mt-4 mb-3"><Icon name="layers" />Tools allowed</h2>
              <div className="row gap-sm wrap">
                {(meta.tools || ['Read', 'Edit', 'Bash']).map(t => (
                  <span key={t} className="chip mono">{t}</span>
                ))}
              </div>
            </>
          )}

          <h2 className="section-title mt-4 mb-3"><Icon name="zap" />Used in</h2>
          {repo ? (
            <div
              className="cd clickable"
              style={{ padding: '.7rem .9rem' }}
              onClick={() => setRoute && setRoute({ page: 'repo', repoId: repo.id, tab: isAgent ? 'agents' : 'skills' })}
              title={`Open ${repo.name}`}
            >
              <div className="row between">
                <div className="row gap-sm">
                  <span className="sb-repo-dot" style={{ '--accent': repo.accent || 'var(--cyan)' }}></span>
                  <span className="tb">{repo.name}</span>
                </div>
                <span className="bg bg-m">{weekCount == null ? '—' : `${weekCount} this week`}</span>
              </div>
            </div>
          ) : (
            <div className="empty">No tracked repo associated.</div>
          )}
        </div>
      </div>
    </>
  );
};

export default AgentDetail;
