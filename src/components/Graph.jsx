import { useState, useEffect, useMemo } from 'react';
import { PageHead } from './Common';
import { useActiveAgents } from '../api';
import NebulaGraph from './NebulaGraph';

// Nebula is the sole delegation-graph renderer. The classic force-directed
// <svg> mode was retired 2026-07-05 (git history has it) -- this file now
// only owns the repo/layer chip state shared with the canvas.
const Graph = ({ repos, onOpen }) => {
  const [selectedRepo, setSelectedRepo] = useState(repos[0]?.id);
  const [layers, setLayers] = useState({ agents: true, skills: true, commands: true, rules: true });
  const liveAgentRows = useActiveAgents(5000);
  const liveRepos = useMemo(() => new Set(liveAgentRows.map(a => a.repo)), [liveAgentRows]);
  useEffect(() => { if (!selectedRepo && repos.length) setSelectedRepo(repos[0].id); }, [repos, selectedRepo]);

  const layerChip = (key, label, swatch) => (
    <span
      key={key}
      className={'chip' + (layers[key] ? ' active' : '')}
      onClick={() => setLayers(l => ({ ...l, [key]: !l[key] }))}
      style={{ opacity: layers[key] ? 1 : .5 }}
    >
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: `var(--${swatch})`, display: 'inline-block', marginRight: 6 }}></span>
      {label}
    </span>
  );

  if (!repos.length) {
    return (
      <>
        <PageHead title="Delegation graph" sub="Force-directed map of how agents, skills, commands and rules connect inside each repo." />
        <div className="empty">No repos tracked yet -- the delegation graph needs at least one repo to render.</div>
      </>
    );
  }

  return (
    <>
      <PageHead
        title="Delegation graph"
        sub="Force-directed map of how agents, skills, commands and rules connect inside each repo. Drag any node to rearrange. Scroll to zoom. Click an agent to inspect. Double-click a leaf robot to fly to its family."
      />
      <div className="row gap-sm wrap mb-2">
        {repos.map(r => (
          <span key={r.id} className={'chip' + (selectedRepo === r.id ? ' active' : '')} onClick={() => setSelectedRepo(r.id)}>
            <span className={'sb-repo-dot' + (liveRepos.has(r.id) ? ' live' : '')} style={{ '--accent': r.accent, width: 6, height: 6 }}></span>
            {r.name}
          </span>
        ))}
      </div>
      <div className="row gap-xs wrap mb-3" style={{ fontSize: '.66rem', color: 'var(--muted)' }}>
        <span style={{ marginRight: 4, alignSelf: 'center' }}>layers:</span>
        {layerChip('agents', 'agents', 'cyan')}
        {layerChip('skills', 'skills', 'gold')}
        {layerChip('commands', 'commands', 'green')}
        {layerChip('rules', 'rules', 'purple')}
      </div>
      <NebulaGraph repos={repos} onOpen={onOpen} selectedRepo={selectedRepo} layers={layers} />
    </>
  );
};

export default Graph;
