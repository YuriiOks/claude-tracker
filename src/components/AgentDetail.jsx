import { useMemo, useState } from 'react';
import Icon from '../icons';
import { Metric, Status, PageHead } from './Common';
import { useAgents, useRepoHtmlArtifacts, useSessions } from '../api';
import MarkdownPanel from './MarkdownPanel';
import { PLUGIN_REGISTRY, MCP_REGISTRY } from '../data';

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

// Local variant of utils/time.js fmtAgo: keeps a linear "Nd ago" bucket for
// multi-day items instead of switching to a calendar-date label. Intentional
// divergence for this invocations list — not a dupe to remove.
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
  // Repo resolution: explicit repoId wins; otherwise find the repo that
  // actually OWNS this item (its agents/skills/commands/rules list contains
  // the name) so a bare /agents/:name link loads the right .claude/ file and
  // scope instead of falling back to global (where the file does not exist).
  const KIND_LIST = { agent: "agents", skill: "skills", command: "commands", rule: "rules" };
  const ownsName = (r) => (r?.[KIND_LIST[kind] || "agents"] || []).includes(name);
  const repo = (repoId && (repos || []).find(r => r.id === repoId))
    || (repos || []).find(r => r.id !== "global" && ownsName(r))
    || (repos || []).find(r => r.id === "global")
    || (repos || [])[0];

  const repoIdFinal = repo?.id ?? null;

  // Derive real "Recent invocations" from sessions filtered by agent name.
  // Real invocation stats come from the backend subagent_call table via
  // AGENT_META (callsToday/callsWeek/callsTotal/recentCalls). The session
  // list only ever contains "main" sessions, so deriving counts from it
  // silently reads 0 for every sub-agent -- kept ONLY as mock-mode fallback.
  const invocations = useMemo(() => {
    const all = (sessions || []).filter(s => s && s.agent === name);
    const scoped = repoIdFinal ? all.filter(s => s.repo === repoIdFinal) : all;
    return scoped.slice(0, 8);
  }, [sessions, name, repoIdFinal]);


  // Now safe to dispatch on kind — every hook has run.
  if (kind === "plugin" || kind === "mcp") {
    const [itemName, itemSource = 'local'] = String(name).split('@');
    const registry = kind === "plugin" ? PLUGIN_REGISTRY : MCP_REGISTRY;
    const info = registry[itemName] || registry[name] || { desc: kind === "plugin" ? "Installed plugin" : "MCP server" };
    const accent = kind === "plugin" ? 'var(--cyan)' : 'var(--purple)';
    const badge = kind === "plugin" ? 'bg-c' : 'bg-p';
    const iconName = kind === "plugin" ? 'pkg' : 'cpu';
    return (
      <>
        <button className="page-back" onClick={onBack}><Icon name="x" size={11} /><span>Back</span></button>
        <PageHead
          title={itemName}
          accent={accent}
          sub={info.desc}
          actions={<>
            <span className={'bg ' + badge}>
              <Icon name={iconName} size={10} />{kind}
            </span>
            {itemSource && itemSource !== 'local' && <span className="bg bg-m">{itemSource}</span>}
            {repo && <span className="bg bg-m">{repo.name}</span>}
          </>}
        />
      </>
    );
  }

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
  // Root/front-door agents (orchestrators) run as the session main agent and
  // dispatch to specialists -- they are never themselves spawned as subagents,
  // so subagent_call has zero rows for them by nature. Detect by name +
  // zero real invocations so we explain rather than show a misleading 0.
  const isRootAgent = isAgent
    && (meta.callsTotal ?? 0) === 0
    && /orchestrat|coordinator|front.?door/i.test(name);


  // No reliable token data on sessions yet — display "—" when missing.
  const avgTokensK = meta.avgTokens ? (meta.avgTokens / 1000).toFixed(1) : null;

  const displayInvocations = (meta.recentCalls && meta.recentCalls.length)
    ? meta.recentCalls.map((c, i) => ({
        id: `${c.sessionId || "call"}-${i}`,
        started: c.startedAt,
        task: `${((c.tokens || 0) / 1000).toFixed(1)}k tokens · session ${c.sessionId}`,
        repo: c.repo,
        status: "done",
        cost: c.cost,
      }))
    : invocations;


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
        <Metric label="Calls today" value={isRootAgent ? "—" : (meta.callsToday ?? "—")} accent="cyan" />
        <Metric label="Avg tokens" value={avgTokensK == null ? '—' : avgTokensK} unit={avgTokensK == null ? '' : 'k'} accent="gold" />
        <Metric label="Calls this week" value={isRootAgent ? "—" : (meta.callsWeek ?? "—")} accent="purple" />
        <Metric
          label="Invocations"
          value={isRootAgent ? "—" : (meta.callsTotal ?? displayInvocations.length)}
          accent="green"
        />
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
            {displayInvocations.length === 0 && (
              <div className="empty">
                {isRootAgent
                  ? "Root agent — runs as the session\u2019s main agent and dispatches to specialists. Its work shows up under the repo\u2019s live sessions, not as subagent invocations, so there are no invocation rows to count."
                  : "No invocations yet."}
              </div>
            )}
            {displayInvocations.map((inv) => (
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
                <span className="bg bg-m">{`${meta.callsWeek ?? 0} this week`}</span>
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
