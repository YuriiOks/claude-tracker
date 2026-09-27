import { memo } from 'react';
import Icon from '../icons';
import { useUser } from '../api';
import { ROUTES } from '../routes';

// R-LAT-9: hoisted so the non-"live" badge case doesn't allocate a fresh
// object per nav item per render (matters once Sidebar is memoized below).
const EMPTY_BADGE_STYLE = {};
const LIVE_BADGE_STYLE = { background: 'var(--live-bg-strong)', color: 'var(--live)' };

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
              aria-label={item.label}
            >
              <Icon name={item.icon} />
              {!collapsed && <span>{item.label}</span>}
              {!collapsed && item.badge ? (
                <span className="badge" style={item.accent === 'live' ? LIVE_BADGE_STYLE : EMPTY_BADGE_STYLE}>
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
              aria-label={r.name}
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
            aria-label="~/.claude"
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
        {!collapsed && user.claudeVersion && (
          <div className="sb-cli" title={`Claude Code v${user.claudeVersion}`}>
            <span className="sb-cli-prompt">$</span>
            <span className="sb-cli-cmd">claude-code</span>
            <span className="sb-cli-ver">v{user.claudeVersion}</span>
          </div>
        )}
      </div>
    </aside>
  );
};

// R-LAT-9: memoized -- App.jsx's live-stream ticks pass a stable `repos`
// array (unchanged reference when nothing changed, see api.js dedupe) so
// this skips re-rendering the whole nav tree on every idle tick.
export default memo(Sidebar);
