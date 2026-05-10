import { useState, useEffect, useMemo } from 'react';
import './styles.css';

import Sidebar from './components/Sidebar';
import { Topbar, PageHead, ViewToggle } from './components/Common';
import Dashboard from './components/Dashboard';
import { ReposPage } from './components/Repos';
import { SessionsPage, LivePage, AgentsPage, PermissionsPanel, PluginsPanel } from './components/Pages';
import { HeatmapPage, CostPage, DiffPage } from './components/Misc';
import Graph from './components/Graph';
import RepoDetail from './components/RepoDetail';
import AgentDetail from './components/AgentDetail';
import { TweaksPanel, TweakSection, TweakRadio, TweakToggle, TweakSelect, useTweaks } from './components/TweaksPanel';

import { useRepos, useGlobal, useSessions, useLiveEvents, useActiveAgents } from './api';

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
  const [route, setRoute] = useState({ page: 'dashboard' });
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const liveEvents = useLiveEvents();
  const { data: rawRepos } = useRepos();
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

    const staticGrid = document.getElementById('staticGrid');
    const staticScan = document.getElementById('staticScan');
    if (staticGrid) staticGrid.style.display = tweaks.showStaticGrid ? '' : 'none';
    if (staticScan) staticScan.style.display = tweaks.showStaticGrid ? '' : 'none';

    document.body.style.fontSize = tweaks.density === 'compact' ? '13px' : tweaks.density === 'cozy' ? '15px' : '14px';

    const bgVal = tweaks.theme === 'light' ? '#fff7ed' : '#070b14';
    document.documentElement.style.setProperty('background-color', bgVal, 'important');
    document.body.style.setProperty('background-color', bgVal, 'important');

    document.documentElement.style.removeProperty('--cyan');
    if (tweaks.theme === 'dark' && tweaks.accentTone && tweaks.accentTone !== 'cyan') {
      const tones = { teal: '#06b6d4', violet: '#a78bfa', rose: '#f472b6', amber: '#fbbf24' };
      if (tones[tweaks.accentTone]) {
        document.documentElement.style.setProperty('--cyan', tones[tweaks.accentTone]);
      }
    }
  }, [tweaks.theme, tweaks.density, tweaks.showStaticGrid, tweaks.terminalSpeed, tweaks.accentTone]);

  const allRepos = useMemo(() => (globalScope ? [...repos, globalScope] : repos), [repos, globalScope]);
  const allLive = repos.filter(r => r.isActive).length;

  const openRepo = (id) => setRoute({ page: 'repo', repoId: id });
  const openAgent = (name, kind) => setRoute({ page: 'agent', name, kind: kind || 'agent' });

  const crumbs = useMemo(() => {
    const map = {
      dashboard: ['Workspace', 'Dashboard'],
      repos: ['Workspace', 'Repositories'],
      live: ['Workspace', 'Live Sessions'],
      sessions: ['Workspace', 'Session Log'],
      agents: ['Workspace', 'Agents & Skills'],
      graph: ['Workspace', 'Delegation Graph'],
      heatmap: ['Workspace', 'Activity Heatmap'],
      cost: ['Workspace', 'Cost & Tokens'],
      permissions: ['Workspace', 'Permissions Audit'],
      plugins: ['Workspace', 'Plugins & MCP'],
      diff: ['Workspace', 'Recent Diffs'],
    };
    if (route.page === 'repo') {
      const r = allRepos.find(r => r.id === route.repoId);
      return ['Workspace', 'Repositories', r?.name || route.repoId];
    }
    if (route.page === 'agent') {
      return ['Workspace', 'Agents & Skills', route.name];
    }
    return map[route.page] || ['Workspace'];
  }, [route]);

  const renderPage = () => {
    switch (route.page) {
      case 'dashboard':
        return <Dashboard repos={repos} sessions={sessions} liveEvents={liveEvents} onOpen={openRepo} />;
      case 'repos':
        return <ReposView repos={repos} onOpen={openRepo} layout={tweaks.reposLayout} />;
      case 'live':
        return <LivePage liveEvents={liveEvents} repos={repos} />;
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
        return <PluginsPanel repo={{ plugins: ['linear', 'slack', 'sentry', 'figma', 'greptile', 'pr-review-toolkit'], mcp: ['filesystem', 'sequential-thinking', 'linear', 'github', 'playwright', 'figma', 'code-review-graph'] }} />;
      case 'diff':
        return <DiffPage />;
      case 'repo': {
        const r = allRepos.find(r => r.id === route.repoId);
        if (!r) return <div className="empty">Repo not found</div>;
        return <RepoDetail repo={r} sessions={sessions} liveEvents={liveEvents} onOpen={openAgent} />;
      }
      case 'agent':
        return <AgentDetail name={route.name} kind={route.kind} repos={allRepos} onBack={() => setRoute({ page: 'agents' })} />;
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
          {renderPage()}
        </div>
      </main>

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
    </>
  );
}

export default App;
