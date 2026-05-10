// Sidebar — workspace nav + identity card

const Sidebar = ({ route, setRoute, repos, allLive, collapsed, setCollapsed }) => {
  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: 'activity' },
    { id: 'repos', label: 'Repositories', icon: 'folder', badge: repos.length },
    { id: 'live', label: 'Live Sessions', icon: 'terminal', badge: allLive, accent: 'live' },
    { id: 'sessions', label: 'Session Log', icon: 'clock' },
    { id: 'agents', label: 'Agents & Skills', icon: 'bot' },
    { id: 'graph', label: 'Delegation Graph', icon: 'git' },
    { id: 'heatmap', label: 'Activity Heatmap', icon: 'cpu' },
    { id: 'cost', label: 'Cost & Tokens', icon: 'dollar' },
    { id: 'permissions', label: 'Permissions Audit', icon: 'shield' },
    { id: 'plugins', label: 'Plugins & MCP', icon: 'plug' },
    { id: 'diff', label: 'Recent Diffs', icon: 'diff' },
  ];

  // Identity surface — wired up to whatever auth provider gets connected later.
  const user = (window.MOCK_DATA && window.MOCK_DATA.USER) || {
    name: 'Yurii Oksamytnyi',
    email: 'yurii@yuriodev.co.uk',
    initials: 'YO',
    plan: 'Pro',
    cliVersion: '2.4.1',
    lastSync: '12s ago',
  };

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
                <span className="badge" style={item.accent === 'live' ? { background: 'rgba(0,255,136,.15)', color: '#00ff88' } : {}}>
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
                style={{ '--accent': r.isActive ? '#00ff88' : r.accent }}></span>
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

      {/* Identity card — pinned to bottom */}
      <div className="sb-user" title={collapsed ? `${user.name} · ${user.email}` : ''}>
        <div className="sb-user-row">
          <div className="sb-avatar">
            <span>{user.initials}</span>
            <span className="sb-avatar-dot" title="Synced"></span>
          </div>
          {!collapsed && (
            <div className="sb-user-meta">
              <div className="sb-user-name">
                {user.name}
                <span className="sb-plan">{user.plan}</span>
              </div>
              <div className="sb-user-email">{user.email}</div>
            </div>
          )}
          {!collapsed && (
            <button className="sb-user-menu" title="Account menu">
              <Icon name="settings" size={12} />
            </button>
          )}
        </div>
        {!collapsed && (
          <div className="sb-cli">
            <span className="sb-cli-prompt">$</span>
            <span className="sb-cli-cmd">claude-code</span>
            <span className="sb-cli-ver">v{user.cliVersion}</span>
            <span className="sb-cli-sync" title={`Last sync: ${user.lastSync}`}>
              <span className="sb-sync-dot"></span>{user.lastSync}
            </span>
          </div>
        )}
      </div>
    </aside>
  );
};

window.Sidebar = Sidebar;
