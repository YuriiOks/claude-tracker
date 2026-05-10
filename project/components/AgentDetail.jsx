// Agent / Skill detail drawer (full-page)

const AgentDetail = ({ name, kind, repos, onBack }) => {
  const meta = (window.MOCK_DATA.AGENT_META || {})[name] || {
    role: kind === 'skill'
      ? 'Skill — encapsulated workflow knowledge that Claude loads when relevant files are touched.'
      : 'Specialist agent — defined in .claude/agents/' + name + '.md.',
    repo: 'global',
    tools: ['Read', 'Edit', 'Bash', 'Grep'],
    callsToday: Math.floor(Math.random() * 18) + 2,
    avgTokens: 2400,
    delegates: [],
  };
  const repo = repos.find(r => r.name === meta.repo) || repos[0];
  const isAgent = kind === 'agent';

  // Mock invocations
  const invocations = [
    { t: '2m', task: 'Audit Bedrock stream parser for empty content blocks', tokens: 4200, status: 'completed', repo: meta.repo },
    { t: '14m', task: 'Generate TypeScript types from OpenAPI spec', tokens: 1800, status: 'completed', repo: meta.repo },
    { t: '38m', task: 'Run ACM-026 test suite end-to-end', tokens: 6300, status: 'running', repo: meta.repo },
    { t: '1h', task: 'Investigate stuck SSE in production', tokens: 8100, status: 'failed', repo: meta.repo },
    { t: '2h', task: 'Add seed migration for new model descriptions', tokens: 2200, status: 'completed', repo: meta.repo },
  ];

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
          <div className="cd" style={{ padding: 0 }}>
            <div className="diff-header"><Icon name="file" size={12} /><span className="mono">.claude/{isAgent ? 'agents' : 'skills'}/{name}{isAgent ? '.md' : '/SKILL.md'}</span></div>
            <div className="code" style={{ borderRadius: 0, border: 'none' }}>
              <span className="cmt">---</span><br />
              <span className="kw">name:</span> <span className="str">{name}</span><br />
              <span className="kw">description:</span> <span className="str">{meta.role.slice(0, 60)}…</span><br />
              {isAgent && <><span className="kw">tools:</span> <span className="str">[{meta.tools.join(', ')}]</span><br /></>}
              {isAgent && <><span className="kw">model:</span> <span className="str">sonnet-4.5</span><br /></>}
              <span className="cmt">---</span><br />
              <br />
              <span className="cmt"># {name}</span><br />
              <br />
              You are a specialist {kind} that handles tasks in the{' '}
              <span className="vr">{meta.repo}</span> codebase.<br />
              <br />
              <span className="cmt">## Responsibilities</span><br />
              {(meta.tools || []).map((t, i) => <span key={i}>- Use <span className="fn">{t}</span> to accomplish your work.<br /></span>)}
              <br />
              <span className="cmt">## When to invoke</span><br />
              Invoke this {kind} when the user asks about {name.split('-').slice(0, 2).join(' ')}…
            </div>
          </div>

          {isAgent && meta.delegates.length > 0 && (
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
                <span className="sb-repo-dot" style={{ '--accent': repo.accent }}></span>
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

window.AgentDetail = AgentDetail;
