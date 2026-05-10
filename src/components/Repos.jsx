import Icon from '../icons';
import { Status } from './Common';

export const RepoCard = ({ repo, onOpen }) => (
  <div className="cd clickable" style={{ '--accent': repo.accent }} onClick={() => onOpen(repo.id)}>
    <div className="cd-bar" style={{ background: `linear-gradient(90deg, ${repo.accent}, transparent)` }}></div>
    <div className="row between mb-2">
      <div className="row gap-sm">
        <span className="sb-repo-dot" style={{ '--accent': repo.isActive ? '#00ff88' : repo.accent }}></span>
        <h3 className="tb">{repo.name}</h3>
      </div>
      {repo.isActive ? <Status kind="running" /> : <Status kind="idle" />}
    </div>
    <div className="row gap-sm mb-3" style={{ fontSize: '.66rem', color: 'var(--muted)' }}>
      <span><Icon name="branch" size={10} /> {repo.branch}</span>
      <span>·</span>
      <span>{repo.language}</span>
    </div>
    <p style={{ fontSize: '.74rem', color: 'var(--txt)', marginBottom: '.8rem', lineHeight: 1.5 }}>{repo.description}</p>

    <div className="grid grid-cols-3 gap-sm" style={{ marginBottom: '.7rem' }}>
      <div>
        <div className="lbl" style={{ fontSize: '.55rem' }}>Sessions</div>
        <div style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--cyan)' }}>{repo.stats.sessionsToday}</div>
        <div style={{ fontSize: '.58rem', color: 'var(--muted)' }}>today · {repo.stats.sessionsWeek} wk</div>
      </div>
      <div>
        <div className="lbl" style={{ fontSize: '.55rem' }}>Tokens</div>
        <div style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--gold)' }}>{(repo.stats.tokensWeek / 1e6).toFixed(2)}M</div>
        <div style={{ fontSize: '.58rem', color: 'var(--muted)' }}>this week</div>
      </div>
      <div>
        <div className="lbl" style={{ fontSize: '.55rem' }}>Cost</div>
        <div style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--green)' }}>${repo.stats.costWeek.toFixed(2)}</div>
        <div style={{ fontSize: '.58rem', color: 'var(--muted)' }}>{repo.stats.filesEdited} files</div>
      </div>
    </div>

    <div className="row wrap gap-xs" style={{ marginTop: 'auto' }}>
      <span className="bg bg-c">{repo.agents.length} agents</span>
      <span className="bg bg-p">{repo.skills.length} skills</span>
      <span className="bg bg-o">{repo.commands.length} cmds</span>
      <span className="bg bg-t">{repo.rules.length} rules</span>
    </div>
  </div>
);

const RepoListRow = ({ repo, onOpen }) => (
  <div className="list-row clickable" style={{ gridTemplateColumns: '14px 1.4fr 1fr .7fr .7fr .7fr 70px' }} onClick={() => onOpen(repo.id)}>
    <span className={'sb-repo-dot' + (repo.isActive ? ' live' : '')} style={{ '--accent': repo.isActive ? '#00ff88' : repo.accent }}></span>
    <div>
      <div className="tb" style={{ fontWeight: 600 }}>{repo.name}</div>
      <div style={{ fontSize: '.62rem', color: 'var(--muted)' }}>{repo.path}</div>
    </div>
    <div className="mono" style={{ fontSize: '.66rem', color: 'var(--muted)' }}>{repo.branch}</div>
    <div>{repo.isActive ? <Status kind="running" /> : <Status kind="idle" />}</div>
    <div className="tc">{repo.stats.sessionsToday} <span className="tm" style={{ fontSize: '.6rem' }}>today</span></div>
    <div className="tg">${repo.stats.costWeek.toFixed(2)}</div>
    <div className="row gap-xs"><span className="bg bg-c">{repo.agents.length}a</span><span className="bg bg-p">{repo.skills.length}s</span></div>
  </div>
);

export const ReposPage = ({ repos, onOpen, layout }) => {
  if (layout === 'list') {
    return (
      <div className="list">
        <div className="list-head" style={{ gridTemplateColumns: '14px 1.4fr 1fr .7fr .7fr .7fr 70px' }}>
          <span></span><span>Repo</span><span>Branch</span><span>Status</span><span>Sessions</span><span>Cost / wk</span><span>Stack</span>
        </div>
        {repos.map(r => <RepoListRow key={r.id} repo={r} onOpen={onOpen} />)}
      </div>
    );
  }
  if (layout === 'board') {
    const cols = [
      { id: 'live', label: 'Live now', filter: r => r.isActive, accent: 'var(--green)' },
      { id: 'idle', label: 'Idle', filter: r => !r.isActive && r.stats.sessionsToday > 0, accent: 'var(--cyan)' },
      { id: 'cold', label: 'No activity today', filter: r => r.stats.sessionsToday === 0, accent: 'var(--muted)' },
    ];
    return (
      <div className="grid grid-cols-3">
        {cols.map(c => (
          <div key={c.id} className="cd" style={{ background: 'var(--card)' }}>
            <div className="row between mb-3">
              <h3 style={{ color: c.accent }}>{c.label}</h3>
              <span className="bg bg-m">{repos.filter(c.filter).length}</span>
            </div>
            <div className="col gap-sm">
              {repos.filter(c.filter).map(r => (
                <div key={r.id} className="cd clickable" style={{ padding: '.65rem' }} onClick={() => onOpen(r.id)}>
                  <div className="row gap-sm mb-2">
                    <span className={'sb-repo-dot' + (r.isActive ? ' live' : '')} style={{ '--accent': r.isActive ? '#00ff88' : r.accent }}></span>
                    <span className="tb" style={{ fontWeight: 600, fontSize: '.78rem' }}>{r.name}</span>
                  </div>
                  <div style={{ fontSize: '.62rem', color: 'var(--muted)' }}>{r.stats.sessionsToday} sessions · ${r.stats.costWeek.toFixed(2)}</div>
                </div>
              ))}
              {repos.filter(c.filter).length === 0 && <div className="empty" style={{ padding: '.9rem' }}>—</div>}
            </div>
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="grid grid-auto">
      {repos.map((r, i) => (
        <div key={r.id} className="rv" style={{ animationDelay: `${i * 0.05}s` }}>
          <RepoCard repo={r} onOpen={onOpen} />
        </div>
      ))}
    </div>
  );
};

export default ReposPage;
