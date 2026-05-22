import { useState, useEffect, useMemo, lazy, Suspense } from 'react';
import './styles.css';

// Eager: shell + default route. These are needed for first paint.
import Sidebar from './components/Sidebar';
import { Topbar, PageHead, ViewToggle } from './components/Common';
import Dashboard from './components/Dashboard';
import { useTweaks } from './components/useTweaks';

// Lazy: every non-default route. Cuts initial JS by ~60% in dev mode where
// each .jsx is its own request.
const ReposPage      = lazy(() => import('./components/Repos').then(m => ({ default: m.ReposPage })));
const SessionsPage   = lazy(() => import('./components/Pages').then(m => ({ default: m.SessionsPage })));
const LivePage       = lazy(() => import('./components/Pages').then(m => ({ default: m.LivePage })));
const AgentsPage     = lazy(() => import('./components/Pages').then(m => ({ default: m.AgentsPage })));
const PermissionsPanel = lazy(() => import('./components/Pages').then(m => ({ default: m.PermissionsPanel })));
const PluginsPanel   = lazy(() => import('./components/Pages').then(m => ({ default: m.PluginsPanel })));
const HeatmapPage    = lazy(() => import('./components/Misc').then(m => ({ default: m.HeatmapPage })));
const CostPage       = lazy(() => import('./components/Misc').then(m => ({ default: m.CostPage })));
const DiffPage       = lazy(() => import('./components/Misc').then(m => ({ default: m.DiffPage })));
const Graph          = lazy(() => import('./components/Graph'));
const RepoDetail     = lazy(() => import('./components/RepoDetail'));
const AgentDetail    = lazy(() => import('./components/AgentDetail'));
const TweaksPanel    = lazy(() => import('./components/TweaksPanel').then(m => ({ default: m.TweaksPanel })));
const TweakSection   = lazy(() => import('./components/TweaksPanel').then(m => ({ default: m.TweakSection })));
const TweakRadio     = lazy(() => import('./components/TweaksPanel').then(m => ({ default: m.TweakRadio })));
const TweakToggle    = lazy(() => import('./components/TweaksPanel').then(m => ({ default: m.TweakToggle })));
const TweakSelect    = lazy(() => import('./components/TweaksPanel').then(m => ({ default: m.TweakSelect })));

import { useRepos, useGlobal, useSessions, useLiveEvents, useActiveAgents } from './api';
import { ROUTE_BY_ID } from './routes';
import { useRoute } from './useRoute';

const TWEAK_DEFAULTS = {
  theme: 'light',
  density: 'cozy',
  showStaticGrid: false,
  terminalSpeed: 'fast',
  accentTone: 'cyan',
  reposLayout: 'board',
};

function ReposView({ repos, onOpen, layout }) {
  const [local, setLocal] = useState(layout || 'grid');
  useEffect(() => setLocal(layout || 'grid'), [layout]);
  return (
    <>
      <PageHead
        title="Repositories"
        sub={`${repos.length} tracked codebases. Each has its own .claude folder with agents, skills, commands, and rules. Click any to drill in.`}
        actions={<ViewToggle
          value={local}
          onChange={setLocal}
          options={[
            { id: 'grid', label: 'Grid', icon: 'grid3' },
            { id: 'list', label: 'List', icon: 'list' },
            { id: 'board', label: 'Board', icon: 'columns' },
          ]}
        />}
      />
      <ReposPage repos={repos} onOpen={onOpen} layout={local} />
    </>
  );
}

function App() {
  const [tweaks, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [route, setRoute, goBack] = useRoute();  // URL routing — pushState + popstate
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const liveEvents = useLiveEvents();
  const { data: rawRepos, loading: reposLoading } = useRepos();
  const { data: globalScope } = useGlobal();
  const { data: sessions } = useSessions(50);
  const liveAgents = useActiveAgents();

  // Merge live activity once at the top so the green dot / "live" badge
  // light up everywhere repos are rendered (sidebar, dashboard, repos page).
  const liveByRepo = useMemo(() => {
    const m = {};
    for (const a of liveAgents) {
      if (!m[a.repo]) m[a.repo] = a; // freshest wins (snapshot is sorted)
    }
    return m;
  }, [liveAgents]);

  const repos = useMemo(
    () => rawRepos.map(r =>
      liveByRepo[r.name] || liveByRepo[r.id] ? { ...r, isActive: true } : r,
    ),
    [rawRepos, liveByRepo],
  );

  useEffect(() => {
    document.documentElement.dataset.theme = tweaks.theme;
    window.__tweakSpeed = tweaks.terminalSpeed;

    // F1: persist theme so the no-flash bootstrap in index.html picks up
    // the user's choice on next load.
    try { localStorage.setItem('claude-tracker-theme', tweaks.theme); } catch { /* private mode */ }

    const staticGrid = document.getElementById('staticGrid');
    const staticScan = document.getElementById('staticScan');
    if (staticGrid) staticGrid.style.display = tweaks.showStaticGrid ? '' : 'none';
    if (staticScan) staticScan.style.display = tweaks.showStaticGrid ? '' : 'none';

    document.body.style.fontSize = tweaks.density === 'compact' ? '13px' : tweaks.density === 'cozy' ? '15px' : '14px';

    // F2: backgrounds are owned by the [data-theme] body rule in styles.css
    // (var(--bg)). The bootstrap script in index.html handles the *initial*
    // paint; CSS owns everything after. Clear any leftover inline override.
    document.documentElement.style.removeProperty('background-color');
    document.body.style.removeProperty('background-color');

    // F4: accent-tone overrides — read from CSS tokens (--tone-*) instead of
    // duplicating hex literals in JS. Tokens are defined in styles.css :root.
    document.documentElement.style.removeProperty('--cyan');
    if (tweaks.theme === 'dark' && tweaks.accentTone && tweaks.accentTone !== 'cyan') {
      const tone = getComputedStyle(document.documentElement)
        .getPropertyValue(`--tone-${tweaks.accentTone}`).trim();
      if (tone) document.documentElement.style.setProperty('--cyan', tone);
    }
  }, [tweaks.theme, tweaks.density, tweaks.showStaticGrid, tweaks.terminalSpeed, tweaks.accentTone]);

  // Keep --sb-w in sync with the sidebar collapse state so backgrounds anchored
  // to var(--sb-w) (#neuralBg, #bg-fill, page-content area) reflow correctly.
  // Widths come from CSS tokens (--sb-w-expanded / --sb-w-collapsed), not hex literals.
  useEffect(() => {
    document.documentElement.style.setProperty(
      '--sb-w',
      sidebarCollapsed ? 'var(--sb-w-collapsed)' : 'var(--sb-w-expanded)',
    );
  }, [sidebarCollapsed]);

  const allRepos = useMemo(() => (globalScope ? [...repos, globalScope] : repos), [repos, globalScope]);
  const allLive = repos.filter(r => r.isActive).length;

  // Sync browser tab title with current route. Mirrors crumbs logic.
  useEffect(() => {
    const base = 'Claude Tracker';
    let title = base;
    if (route.page === 'repo') {
      const r = allRepos.find(rr => rr.id === route.repoId);
      title = `${r?.name || route.repoId} · ${base}`;
    } else if (route.page === 'agent') {
      title = `${route.name} · ${base}`;
    } else {
      const r = ROUTE_BY_ID[route.page];
      if (r) title = `${r.label} · ${base}`;
    }
    document.title = title;
  }, [route, allRepos]);

  const openRepo = (id) => setRoute({ page: 'repo', repoId: id });
  const openAgent = (name, kind) => setRoute({ page: 'agent', name, kind: kind || 'agent' });

  // F16: crumbs derived from the same ROUTES registry that Sidebar uses
  const crumbs = useMemo(() => {
    if (route.page === 'repo') {
      const r = allRepos.find(rr => rr.id === route.repoId);
      return ['Workspace', ROUTE_BY_ID.repos.label, r?.name || route.repoId];
    }
    if (route.page === "agent") {
      if (route.repoId) {
        const r = allRepos.find(rr => rr.id === route.repoId);
        return ["Workspace", ROUTE_BY_ID.repos.label, r?.name || route.repoId, route.name];
      }
      return ["Workspace", ROUTE_BY_ID.agents.label, route.name];
    }
    const r = ROUTE_BY_ID[route.page];
    return r ? ['Workspace', r.label] : ['Workspace'];
  }, [route, allRepos]);

  const renderPage = () => {
    switch (route.page) {
      case 'dashboard':
        return <Dashboard repos={repos} sessions={sessions} liveEvents={liveEvents} onOpen={openRepo} setRoute={setRoute} />;
      case 'repos':
        return <ReposView repos={repos} onOpen={openRepo} layout={tweaks.reposLayout} />;
      case 'live':
        return <LivePage liveEvents={liveEvents} repos={repos} onOpen={openRepo} />;
      case 'sessions':
        return <SessionsPage sessions={sessions} repos={repos} />;
      case 'agents':
        return <AgentsPage repos={allRepos} onOpen={openAgent} />;
      case 'graph':
        return <Graph repos={repos} onOpen={openAgent} />;
      case 'heatmap':
        return <HeatmapPage repos={repos} />;
      case 'cost':
        return <CostPage repos={repos} />;
      case 'permissions':
        return <PermissionsPanel scope="all repos" />;
      case 'plugins':
        // F7: use the real global scope (plugins/mcp loaded via useGlobal), not a hardcoded mock
        return <PluginsPanel repo={globalScope} />;
      case 'diff':
        return <DiffPage />;
      case 'repo': {
        const r = allRepos.find(rr => rr.id === route.repoId);
        if (!r) {
          return reposLoading
            ? <div className="empty">Loading repo…</div>
            : <div className="empty">Repo not found</div>;
        }
        return (
          <RepoDetail
            repo={r}
            sessions={sessions}
            liveEvents={liveEvents}
            tab={route.tab || 'overview'}
            onTabChange={(tab) => setRoute({ page: 'repo', repoId: r.id, tab })}
            // In-repo drill-in carries repoId so URL is /repos/:id/<tab>/:name
            onOpen={(name, kind) => setRoute({ page: 'agent', name, kind: kind || 'agent', repoId: r.id })}
          />
        );
      }
      case 'agent': {
        // Back target: in-repo → repo's matching tab; global → /agents
        const KIND_TAB = { agent: 'agents', skill: 'skills', command: 'commands', rule: 'rules' };
        const back = route.repoId
          ? { page: 'repo', repoId: route.repoId, tab: KIND_TAB[route.kind] || 'agents' }
          : { page: 'agents' };
        return <AgentDetail name={route.name} kind={route.kind} repos={allRepos} repoId={route.repoId} onBack={() => goBack(back)} setRoute={setRoute} />;
      }
      default:
        return <div>404</div>;
    }
  };

  return (
    <>
      <Sidebar route={route} setRoute={setRoute} repos={repos} allLive={allLive} collapsed={sidebarCollapsed} setCollapsed={setSidebarCollapsed} />
      <main className="main">
        <Topbar
          crumbs={crumbs}
          theme={tweaks.theme}
          setTheme={(t) => setTweak('theme', t)}
          allLive={allLive}
          onOpenTweaks={() => window.postMessage({ type: '__activate_edit_mode' }, '*')}
        />
        <div className="content" key={JSON.stringify(route)}>
          <Suspense fallback={<div className="empty" style={{ padding: '2rem', color: 'var(--muted)' }}>Loading…</div>}>
            {renderPage()}
          </Suspense>
        </div>
      </main>

      <Suspense fallback={null}>
      <TweaksPanel>
        <TweakSection label="Theme">
          <TweakRadio
            label="Mode"
            value={tweaks.theme}
            onChange={v => setTweak('theme', v)}
            options={[{ value: 'dark', label: 'Dark' }, { value: 'light', label: 'Light' }]}
          />
          <TweakSelect
            label="Accent tone (dark)"
            value={tweaks.accentTone}
            onChange={v => setTweak('accentTone', v)}
            options={[
              { value: 'cyan', label: 'Cyan (default)' },
              { value: 'teal', label: 'Teal' },
              { value: 'violet', label: 'Violet' },
              { value: 'rose', label: 'Rose' },
              { value: 'amber', label: 'Amber' },
            ]}
          />
        </TweakSection>
        <TweakSection label="Layout">
          <TweakRadio
            label="Density"
            value={tweaks.density}
            onChange={v => setTweak('density', v)}
            options={[
              { value: 'compact', label: 'Compact' },
              { value: 'comfy', label: 'Comfy' },
              { value: 'cozy', label: 'Cozy' },
            ]}
          />
          <TweakRadio
            label="Repos page"
            value={tweaks.reposLayout}
            onChange={v => setTweak('reposLayout', v)}
            options={[
              { value: 'grid', label: 'Grid' },
              { value: 'list', label: 'List' },
              { value: 'board', label: 'Board' },
            ]}
          />
        </TweakSection>
        <TweakSection label="Atmosphere">
          <TweakToggle label="Static grid + scanlines" value={tweaks.showStaticGrid} onChange={v => setTweak('showStaticGrid', v)} />
          <TweakRadio
            label="Live feed speed"
            value={tweaks.terminalSpeed}
            onChange={v => setTweak('terminalSpeed', v)}
            options={[
              { value: 'slow', label: 'Slow' },
              { value: 'normal', label: 'Normal' },
              { value: 'fast', label: 'Fast' },
            ]}
          />
        </TweakSection>
      </TweaksPanel>
      </Suspense>
    </>
  );
}

export default App;
