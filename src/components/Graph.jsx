import { useState, useEffect, useRef, useMemo } from 'react';
import { PageHead } from './Common';
import { useAgents, useFileSizes } from '../api';

const Graph = ({ repos, onOpen }) => {
  const W = 900, H = 540;
  const [selectedRepo, setSelectedRepo] = useState(repos[0]?.id);
  const [layers, setLayers] = useState({ agents: true, skills: true, commands: true, rules: true });
  const repo = repos.find(r => r.id === selectedRepo) || repos[0];
  const { data: AGENT_META } = useAgents();
  const FILE_SIZES = useFileSizes();

  const { initialNodes, edges } = useMemo(() => {
    const ns = [];
    const agentMeta = AGENT_META;

    ns.push({ id: '__repo__', label: repo.name, kind: 'repo', r: 34, color: repo.accent, fx: W / 2, fy: H / 2 });

    const skillAgents = (skill) => {
      const tokens = skill.toLowerCase().split('-');
      return repo.agents.filter(a => tokens.some(t => a.toLowerCase().includes(t) && t.length > 3));
    };

    const SIZES = FILE_SIZES;
    const sizeFor = (kind, name, fallbackBytes) => {
      const bytes = SIZES[kind]?.[name] ?? fallbackBytes;
      const k = Math.sqrt(Math.max(0.2, bytes / 1000));
      // File-size-based ranges: [min, max, sqrt-multiplier]
      // Kept small so the central repo node (r=34) reads as the focus.
      const ranges = {
        agent:   [4, 11, 3.0],
        skill:   [3.5, 10, 2.8],
        command: [3, 7, 2.0],
        rule:    [3, 8, 2.2],
      };
      const [lo, hi, mult] = ranges[kind] || [10, 18, 5];
      return { r: Math.max(lo, Math.min(hi, lo + k * mult)), bytes };
    };

    if (layers.agents) {
      repo.agents.forEach((a, i) => {
        const calls = agentMeta[a]?.callsToday ?? 1;
        const { r, bytes } = sizeFor('agent', a, 3000);
        const ang = (i / repo.agents.length) * Math.PI * 2 - Math.PI / 2;
        ns.push({
          id: 'a-' + a, label: a, kind: 'agent',
          x: W / 2 + Math.cos(ang) * 160,
          y: H / 2 + Math.sin(ang) * 160,
          r, color: 'cyan', meta: { callsToday: calls, bytes },
        });
      });
    }

    if (layers.skills) {
      repo.skills.forEach((s, i) => {
        const matches = skillAgents(s).length;
        const { r, bytes } = sizeFor('skill', s, 4000);
        const ang = (i / repo.skills.length) * Math.PI * 2 - Math.PI / 2 + (Math.PI / repo.skills.length);
        ns.push({
          id: 's-' + s, label: s, kind: 'skill',
          x: W / 2 + Math.cos(ang) * 250,
          y: H / 2 + Math.sin(ang) * 250,
          r, color: 'purple', meta: { usedBy: matches, bytes },
        });
      });
    }

    if (layers.commands) {
      (repo.commands || []).forEach((c, i) => {
        const { r, bytes } = sizeFor('command', c, 800);
        const ang = (i / Math.max(1, (repo.commands || []).length)) * Math.PI * 2 + Math.PI / 6;
        ns.push({
          id: 'c-' + c, label: c, kind: 'command',
          x: W / 2 + Math.cos(ang) * 320,
          y: H / 2 + Math.sin(ang) * 200,
          r, color: 'green', meta: { bytes },
        });
      });
    }

    if (layers.rules) {
      (repo.rules || []).forEach((rl, i) => {
        const { r, bytes } = sizeFor('rule', rl, 1500);
        const ang = (i / Math.max(1, (repo.rules || []).length)) * Math.PI * 2 - Math.PI / 3;
        ns.push({
          id: 'r-' + rl, label: rl, kind: 'rule',
          x: W / 2 + Math.cos(ang) * 290,
          y: H / 2 + Math.sin(ang) * 220,
          r, color: 'gold', meta: { bytes },
        });
      });
    }

    const es = [];
    if (layers.agents) {
      repo.agents.forEach(a => es.push({ from: '__repo__', to: 'a-' + a, kind: 'owns' }));
      repo.agents.forEach(a => {
        const m = agentMeta[a];
        (m?.delegates || []).forEach(d => {
          if (repo.agents.includes(d)) es.push({ from: 'a-' + a, to: 'a-' + d, kind: 'delegate' });
        });
      });
    }
    if (layers.skills) {
      repo.skills.forEach(s => {
        const matches = skillAgents(s);
        if (matches.length) {
          if (layers.agents) es.push({ from: 'a-' + matches[0], to: 's-' + s, kind: 'uses' });
          else es.push({ from: '__repo__', to: 's-' + s, kind: 'uses' });
        } else {
          es.push({ from: '__repo__', to: 's-' + s, kind: 'uses' });
        }
      });
    }
    if (layers.commands) {
      (repo.commands || []).forEach(c => es.push({ from: '__repo__', to: 'c-' + c, kind: 'entry' }));
    }
    if (layers.rules) {
      (repo.rules || []).forEach(r => es.push({ from: '__repo__', to: 'r-' + r, kind: 'context' }));
    }

    return { initialNodes: ns, edges: es };
  }, [repo, layers, AGENT_META, FILE_SIZES]);

  const nodesRef = useRef([]);
  const [, force] = useState(0);
  const [hover, setHover] = useState(null);
  const [dragging, setDragging] = useState(null);
  const svgRef = useRef(null);

  useEffect(() => {
    nodesRef.current = initialNodes.map(n => ({ ...n, vx: 0, vy: 0, x: n.fx ?? n.x, y: n.fy ?? n.y }));
    force(t => t + 1);
  }, [initialNodes]);

  useEffect(() => {
    let raf;
    const step = () => {
      const ns = nodesRef.current;
      if (!ns.length) { raf = requestAnimationFrame(step); return; }

      for (let i = 0; i < ns.length; i++) {
        for (let j = i + 1; j < ns.length; j++) {
          const a = ns[i], b = ns[j];
          let dx = b.x - a.x, dy = b.y - a.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 1) { d2 = 1; dx = .5; dy = .5; }
          const d = Math.sqrt(d2);
          const f = 2200 / d2;
          const fx = (dx / d) * f, fy = (dy / d) * f;
          if (a.fx == null) { a.vx -= fx; a.vy -= fy; }
          if (b.fx == null) { b.vx += fx; b.vy += fy; }
        }
      }

      const restLen = (e) => {
        if (e.kind === 'owns') return 150;
        if (e.kind === 'uses') return 110;
        if (e.kind === 'entry') return 230;
        if (e.kind === 'context') return 210;
        if (e.kind === 'delegate') return 130;
        return 150;
      };
      edges.forEach(e => {
        const a = ns.find(n => n.id === e.from);
        const b = ns.find(n => n.id === e.to);
        if (!a || !b) return;
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.sqrt(dx * dx + dy * dy) || .001;
        const k = (e.kind === 'entry' || e.kind === 'context') ? 0.025 : 0.04;
        const f = (d - restLen(e)) * k;
        const fx = (dx / d) * f, fy = (dy / d) * f;
        if (a.fx == null) { a.vx += fx; a.vy += fy; }
        if (b.fx == null) { b.vx -= fx; b.vy -= fy; }
      });

      ns.forEach(n => {
        if (n.fx != null) return;
        n.vx += (W / 2 - n.x) * 0.0015;
        n.vy += (H / 2 - n.y) * 0.0015;
      });

      ns.forEach(n => {
        if (n.fx != null) { n.x = n.fx; n.y = n.fy; n.vx = 0; n.vy = 0; return; }
        n.vx *= 0.85; n.vy *= 0.85;
        n.x += n.vx; n.y += n.vy;
        const m = n.r + 30;
        if (n.x < m) { n.x = m; n.vx *= -.4; }
        if (n.x > W - m) { n.x = W - m; n.vx *= -.4; }
        if (n.y < m) { n.y = m; n.vy *= -.4; }
        if (n.y > H - m) { n.y = H - m; n.vy *= -.4; }
      });

      force(t => (t + 1) % 100000);
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [edges]);

  const didDragRef = useRef(false);
  const downPosRef = useRef(null);

  const getMouse = (evt) => {
    const svg = svgRef.current;
    const pt = svg.createSVGPoint();
    pt.x = evt.clientX; pt.y = evt.clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) return { x: 0, y: 0 };
    const t = pt.matrixTransform(ctm.inverse());
    return { x: t.x, y: t.y };
  };

  const onPointerDown = (n) => (e) => {
    if (n.id === '__repo__') return;
    e.preventDefault();
    const node = nodesRef.current.find(x => x.id === n.id);
    if (!node) return;
    node.fx = node.x; node.fy = node.y;
    didDragRef.current = false;
    downPosRef.current = { x: e.clientX, y: e.clientY };
    setDragging(n.id);
    e.target.setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e) => {
    if (!dragging) return;
    if (downPosRef.current) {
      const dx = e.clientX - downPosRef.current.x;
      const dy = e.clientY - downPosRef.current.y;
      if (Math.hypot(dx, dy) > 4) didDragRef.current = true;
    }
    const pos = getMouse(e);
    const node = nodesRef.current.find(x => x.id === dragging);
    if (node) { node.fx = pos.x; node.fy = pos.y; }
  };
  const onPointerUp = () => {
    if (!dragging) return;
    const node = nodesRef.current.find(x => x.id === dragging);
    if (node && dragging !== '__repo__') { node.fx = null; node.fy = null; }
    setDragging(null);
    setTimeout(() => { didDragRef.current = false; }, 0);
  };

  const resolve = (c) => c.startsWith('#') ? c : `var(--${c})`;
  const nodes = nodesRef.current.length ? nodesRef.current : initialNodes;

  const glyph = (kind) => kind === 'agent' ? '◆' : kind === 'skill' ? '✦' : kind === 'command' ? '/' : kind === 'rule' ? '§' : '';

  const edgeStyle = (kind, active) => {
    if (active) return { stroke: 'var(--cyan)', width: 1.8, opacity: 1, dash: '' };
    switch (kind) {
      case 'delegate': return { stroke: 'var(--gold)', width: 1.2, opacity: .75, dash: '' };
      case 'uses':     return { stroke: 'var(--purple)', width: 1, opacity: .55, dash: '' };
      case 'entry':    return { stroke: 'var(--green)', width: 1, opacity: .45, dash: '4 5' };
      case 'context':  return { stroke: 'var(--gold)', width: 1, opacity: .35, dash: '1 4' };
      default:         return { stroke: 'var(--brd)', width: 1, opacity: .42, dash: '' };
    }
  };

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

  return (
    <>
      <PageHead title="Delegation graph" sub="Force-directed map of how agents, skills, commands and rules connect inside each repo. Node size encodes activity for agents and reach for skills. Drag any node to rearrange. Hover to highlight links. Click an agent to inspect." />

      <div className="row gap-sm wrap mb-2">
        {repos.map(r => (
          <span key={r.id} className={'chip' + (selectedRepo === r.id ? ' active' : '')} onClick={() => setSelectedRepo(r.id)}>
            <span className="sb-repo-dot" style={{ '--accent': r.accent, width: 6, height: 6 }}></span>
            {r.name}
          </span>
        ))}
      </div>

      <div className="row gap-xs wrap mb-3" style={{ fontSize: '.66rem', color: 'var(--muted)' }}>
        <span style={{ marginRight: 4, alignSelf: 'center' }}>layers:</span>
        {layerChip('agents', 'agents', 'cyan')}
        {layerChip('skills', 'skills', 'purple')}
        {layerChip('commands', 'commands', 'green')}
        {layerChip('rules', 'rules', 'gold')}
      </div>

      <div className="graph-wrap" style={{ touchAction: 'none' }}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="xMidYMid meet"
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
          style={{ cursor: dragging ? 'grabbing' : 'default' }}
        >
          <defs>
            <marker id="ah-gold" markerWidth="6" markerHeight="6" refX="6" refY="3" orient="auto">
              <polygon points="0 0, 6 3, 0 6" fill="var(--gold)" />
            </marker>
            <radialGradient id="repoGlow">
              <stop offset="0%" stopColor={repo.accent} stopOpacity=".35" />
              <stop offset="100%" stopColor={repo.accent} stopOpacity="0" />
            </radialGradient>
          </defs>

          <circle
            cx={nodes.find(n => n.id === '__repo__')?.x || W / 2}
            cy={nodes.find(n => n.id === '__repo__')?.y || H / 2}
            r="90"
            fill="url(#repoGlow)"
            style={{ pointerEvents: 'none' }}
          />

          {edges.map((e, i) => {
            const a = nodes.find(n => n.id === e.from);
            const b = nodes.find(n => n.id === e.to);
            if (!a || !b) return null;
            const active = hover && (hover === e.from || hover === e.to);
            const s = edgeStyle(e.kind, active);
            return (
              <g key={i}>
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                  stroke={s.stroke} strokeWidth={s.width} strokeOpacity={s.opacity} strokeDasharray={s.dash}
                  markerEnd={e.kind === 'delegate' ? 'url(#ah-gold)' : ''} />
                {e.kind === 'delegate' && !active && (
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke="var(--gold)" strokeWidth="1.4" strokeOpacity="0.55" strokeDasharray="3 14"
                    style={{ filter: 'drop-shadow(0 0 3px var(--gold))' }}>
                    <animate attributeName="stroke-dashoffset" from="17" to="0" dur="1.6s" repeatCount="indefinite" />
                  </line>
                )}
                {active && (
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke="var(--cyan)" strokeWidth="2.5" strokeOpacity="0.9" strokeDasharray="4 18"
                    style={{ filter: 'drop-shadow(0 0 4px var(--cyan))' }}>
                    <animate attributeName="stroke-dashoffset" from="22" to="0" dur="0.9s" repeatCount="indefinite" />
                  </line>
                )}
              </g>
            );
          })}

          {nodes.map(n => {
            const isHovered = hover === n.id;
            const isDimmed = hover && hover !== n.id && !edges.some(e =>
              (e.from === hover && e.to === n.id) || (e.to === hover && e.from === n.id)
            );
            const color = resolve(n.color);
            const isRepo = n.kind === 'repo';
            const isSmall = n.kind === 'command' || n.kind === 'rule';
            const labelText = n.kind === 'command'
              ? n.label.replace(/^\//, '/')
              : n.label.length > 22 ? n.label.slice(0, 20) + '…' : n.label;
            return (
              <g
                key={n.id}
                transform={`translate(${n.x}, ${n.y})`}
                onMouseEnter={() => setHover(n.id)}
                onMouseLeave={() => setHover(null)}
                onPointerDown={onPointerDown(n)}
                onClick={() => !didDragRef.current && n.kind === 'agent' && onOpen && onOpen(n.label, 'agent')}
                style={{
                  opacity: isDimmed ? .25 : 1,
                  cursor: isRepo ? 'default' : (dragging === n.id ? 'grabbing' : (n.kind === 'agent' ? 'pointer' : 'grab')),
                  transition: 'opacity .25s',
                }}
              >
                {isHovered && !isRepo && (
                  <circle r={n.r} fill="none" stroke={color} strokeWidth="1.5" opacity="0.6">
                    <animate attributeName="r" from={n.r} to={n.r * 2} dur="1.2s" repeatCount="indefinite" />
                    <animate attributeName="opacity" from="0.7" to="0" dur="1.2s" repeatCount="indefinite" />
                  </circle>
                )}
                <circle r={n.r} fill={color} fillOpacity={isHovered ? .28 : (isSmall ? .1 : .14)}
                  stroke={color} strokeWidth={isHovered ? 2 : (isSmall ? 1 : 1.5)}
                  style={{ transition: 'fill-opacity .2s, stroke-width .2s' }} />
                {isRepo ? (
                  <text textAnchor="middle" dy="5" fontWeight="700" fontSize="14" fill="var(--txt-bright)">{n.label}</text>
                ) : (
                  <>
                    <text textAnchor="middle" dy={isSmall ? '3' : '3.5'} fontSize={isSmall ? '9' : '11'} fontWeight="700" fill={color}>{glyph(n.kind)}</text>
                    <rect x={-(Math.min(labelText.length, 24) * 3.4)} y={n.r + 5}
                      width={Math.min(labelText.length, 24) * 6.8} height={14} rx={3}
                      fill="var(--card)" stroke="var(--brd2)" strokeWidth=".5" />
                    <text textAnchor="middle" dy={n.r + 15} fontSize="10" fontWeight="500" fill="var(--txt-bright)">{labelText}</text>
                  </>
                )}
                {n.kind === 'agent' && n.meta?.callsToday > 0 && !isHovered && (
                  <g transform={`translate(${n.r * 0.7}, ${-n.r * 0.7})`}>
                    <circle r="7" fill="var(--card)" stroke={color} strokeWidth="1" />
                    <text textAnchor="middle" dy="3" fontSize="8" fontWeight="700" fill={color}>{n.meta.callsToday}</text>
                  </g>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {hover && (() => {
        const n = nodes.find(x => x.id === hover);
        if (!n || n.kind === 'repo') return null;
        const kb = n.meta?.bytes ? (n.meta.bytes / 1024).toFixed(1) + ' KB' : '';
        const detail =
          n.kind === 'agent'   ? `agent · ${kb} · ${n.meta?.callsToday ?? 0} calls today` :
          n.kind === 'skill'   ? `skill · ${kb} · used by ${n.meta?.usedBy ?? 0} agent${(n.meta?.usedBy ?? 0) === 1 ? '' : 's'}` :
          n.kind === 'command' ? `slash command · ${kb} · entry point` :
          n.kind === 'rule'    ? `rule · ${kb} · auto-loaded context` : '';
        return (
          <div className="row gap-sm mt-2" style={{ fontSize: '.7rem', color: 'var(--muted)' }}>
            <strong style={{ color: 'var(--txt-bright)' }}>{n.label}</strong>
            <span>·</span>
            <span>{detail}</span>
          </div>
        );
      })()}

      <div className="mt-3" style={{ fontSize: '.68rem', color: 'var(--muted)', lineHeight: 1.7 }}>
        <div className="row gap-md wrap">
          <span><span style={{ color: 'var(--cyan)', fontWeight: 700 }}>◆</span> agent</span>
          <span><span style={{ color: 'var(--purple)', fontWeight: 700 }}>✦</span> skill</span>
          <span><span style={{ color: 'var(--green)', fontWeight: 700 }}>/</span> command</span>
          <span><span style={{ color: 'var(--gold)', fontWeight: 700 }}>§</span> rule</span>
          <span style={{ opacity: .65 }}>· node size = file size on disk (sqrt-scaled)</span>
        </div>
        <div className="row gap-md wrap mt-1">
          <span><span style={{ color: 'var(--gold)' }}>→</span> agent delegates to agent</span>
          <span><span style={{ color: 'var(--purple)' }}>—</span> agent uses skill</span>
          <span><span style={{ color: 'var(--green)', letterSpacing: 2 }}>- -</span> command entry point</span>
          <span><span style={{ color: 'var(--gold)', letterSpacing: 2 }}>· ·</span> rule context</span>
          <span style={{ marginLeft: 'auto' }}>drag nodes to rearrange · {nodes.length} nodes · {edges.length} edges</span>
        </div>
      </div>
    </>
  );
};

export default Graph;
