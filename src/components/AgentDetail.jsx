import { useMemo, useState } from 'react';
import Icon from '../icons';
import { Metric, Status, PageHead } from './Common';
import { useAgents, useRepoHtmlArtifacts } from '../api';
import { AGENT_INVOCATIONS } from '../data';
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
          defaultMode="code"
          emptyMessage={isCmd ? 'Command file not found in repo.' : 'Rule file not found in repo.'}
        />
      </div>
    </>
  );
};

const AgentDetail = ({ name, kind, repos, repoId, onBack }) => {
  // Hooks must run unconditionally — call them first, then dispatch on kind.
  const { data: AGENT_META } = useAgents();
  const defaultCallsToday = useMemo(() => Math.floor(Math.random() * 18) + 2, [name]);
  // For commands and rules we render a simpler view (no calls/tokens schema).
  if (kind === 'command' || kind === 'rule') {
    const repo = (repos || []).find(r => r.id === repoId) || (repos || []).find(r => r.id === 'global') || (repos || [])[0];
    return <SimpleItemDetail name={name} kind={kind} repo={repo} onBack={onBack} />;
  }
  const meta = (AGENT_META && AGENT_META[name]) || {
    role: kind === 'skill'
      ? 'Skill — encapsulated workflow knowledge that Claude loads when relevant files are touched.'
      : 'Specialist agent — defined in .claude/agents/' + name + '.md.',
    repo: 'global',
    tools: ['Read', 'Edit', 'Bash', 'Grep'],
    callsToday: defaultCallsToday,
    avgTokens: 2400,
    delegates: [],
  };
  // Prefer the URL's repoId (set by App.jsx when navigated via /repos/:id/...);
  // fall back to the mock meta.repo only for top-level /agents/:name routes.
  const repo = (repoId && repos.find(r => r.id === repoId))
    || repos.find(r => r.name === meta.repo)
    || repos[0];
  const isAgent = kind === 'agent';

  // F12: invocations sample sourced from data.js (was inline)
  const invocations = AGENT_INVOCATIONS.map(inv => ({ ...inv, repo: meta.repo }));

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
          <span className="bg bg-m">{meta.repo}</span>
        </>}
      />

      <div className="grid grid-cols-4 mb-4">
        <Metric label="Calls today" value={meta.callsToday} accent="cyan" />
        <Metric label="Avg tokens" value={(meta.avgTokens / 1000).toFixed(1)} unit="k" accent="gold" />
        <Metric label="Total this week" value={meta.callsToday * 7} accent="purple" />
        <Metric label="Est. cost / wk" value={`$${((meta.callsToday * 7 * meta.avgTokens / 1e6) * 8).toFixed(2)}`} accent="green" />
      </div>

      <div className="split">
        <div>
          <h2 className="section-title mb-3"><Icon name="file" />Definition</h2>
          <MarkdownPanel
            repoId={repo?.id}
            relPath={'.claude/' + (isAgent ? 'agents' : 'skills') + '/' + name + (isAgent ? '.md' : '/SKILL.md')}
            filePath={'.claude/' + (isAgent ? 'agents' : 'skills') + '/' + name + (isAgent ? '.md' : '/SKILL.md')}
            defaultMode="code"
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
            {invocations.map((inv, i) => (
              <div key={i} className="list-row" style={{ gridTemplateColumns: '50px 1fr 70px 80px' }}>
                <span className="mono" style={{ fontSize: '.62rem', color: 'var(--muted)' }}>{inv.t} ago</span>
                <div>
                  <div style={{ fontSize: '.72rem', color: 'var(--txt-bright)' }}>{inv.task}</div>
                  <div style={{ fontSize: '.6rem', color: 'var(--muted)' }}>{inv.repo}</div>
                </div>
                <Status kind={inv.status} />
                <span className="tg" style={{ fontSize: '.7rem' }}>{(inv.tokens / 1000).toFixed(1)}k</span>
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
          <div className="cd" style={{ padding: '.7rem .9rem' }}>
            <div className="row between">
              <div className="row gap-sm">
                <span className="sb-repo-dot" style={{ '--accent': repo?.accent || 'var(--cyan)' }}></span>
                <span className="tb">{meta.repo}</span>
              </div>
              <span className="bg bg-m">{meta.callsToday * 7} invocations</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default AgentDetail;
