import Icon from '../icons';
import { useUser } from '../api';
import { ROUTES } from '../routes';

const Sidebar = ({ route, setRoute, repos, allLive, collapsed, setCollapsed }) => {
  const { data: user } = useUser();
  // F16: nav items sourced from src/routes.js; badge keys resolved here
  const badgeMap = { repoCount: repos.length, liveCount: allLive };
  const navItems = ROUTES.map(r => ({
    ...r,
    badge: r.badgeKey ? badgeMap[r.badgeKey] : undefined,
  }));

  return (
    <aside className={'sidebar' + (collapsed ? ' collapsed' : '')}>
      <div className="sb-brand">
        <div className="sb-logo">CC</div>
        {!collapsed && (
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="sb-name">Claude Code</div>
            <div className="sb-tag">Tracker</div>
          </div>
        )}
        <button
          className="sb-collapse"
          onClick={() => setCollapsed(!collapsed)}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <Icon name={collapsed ? 'chevronRight' : 'chevronLeft'} size={12} />
        </button>
      </div>

      <div className="sb-scroll">
        {!collapsed && <div className="sb-section">Workspace</div>}
        <div className="sb-nav">
          {navItems.map(item => (
            <button
              key={item.id}
              className={'sb-item' + (route.page === item.id ? ' active' : '')}
              onClick={() => setRoute({ page: item.id })}
              title={collapsed ? item.label : ''}
            >
              <Icon name={item.icon} />
              {!collapsed && <span>{item.label}</span>}
              {!collapsed && item.badge ? (
                <span className="badge" style={item.accent === 'live' ? { background: 'var(--live-bg-strong)', color: 'var(--live)' } : {}}>
                  {item.badge}
                </span>
              ) : null}
            </button>
          ))}
        </div>

        {!collapsed && <div className="sb-section">Tracked Repos</div>}
        <div className="sb-nav">
          {repos.map(r => (
            <button
              key={r.id}
              className={'sb-item' + (route.page === 'repo' && route.repoId === r.id ? ' active' : '')}
              onClick={() => setRoute({ page: 'repo', repoId: r.id })}
              title={collapsed ? r.name : ''}
            >
              <span className={'sb-repo-dot' + (r.isActive ? ' live' : '')}
                style={{ '--accent': r.isActive ? 'var(--live)' : r.accent }}></span>
              {!collapsed && <span>{r.name}</span>}
            </button>
          ))}
        </div>

        {!collapsed && <div className="sb-section sb-section-sub">Global config</div>}
        <div className="sb-nav">
          <button
            className={'sb-item sb-item-global' + (route.page === 'repo' && route.repoId === 'global' ? ' active' : '')}
            onClick={() => setRoute({ page: 'repo', repoId: 'global' })}
            title={collapsed ? '~/.claude' : ''}
          >
            <Icon name="hash" />
            {!collapsed && <span className="mono">~/.claude</span>}
          </button>
        </div>
      </div>

      <div className="sb-user" title={collapsed ? `${user.name} · ${user.email}` : ''}>
        <div className="sb-user-row">
          <div className="sb-avatar">
            <span>{user.initials}</span>
          </div>
          {!collapsed && (
            <div className="sb-user-meta">
              <div className="sb-user-name">{user.name}</div>
              <div className="sb-user-email">{user.email}</div>
            </div>
          )}
          {!collapsed && (
            <button
              className="sb-user-menu"
              title="Open settings"
              onClick={() => window.postMessage({ type: '__activate_edit_mode' }, '*')}
            >
              <Icon name="settings" size={12} />
            </button>
          )}
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
