/**
 * LiveGraph — radial force-layout graph showing the active agent + its recent
 * tool calls for a given repo. Styled like the RUBRIC Console: dark field,
 * hex-grid background, pixel-art Space Invaders avatars, animated pulse lines.
 *
 * Uses no external deps (no D3, no canvas). Pure SVG + CSS animations.
 */
import { useRepoEvents } from '../api';

// ── Pixel-art sprite data ─────────────────────────────────────────────────────
// Each sprite: 11 cols × 8 rows.  1 = filled pixel, 0 = transparent.
const SPRITES = {
  main: [
    [0,0,0,1,1,1,1,1,0,0,0],
    [0,0,1,1,1,1,1,1,1,0,0],
    [0,1,1,0,1,1,1,0,1,1,0],
    [1,1,1,1,1,1,1,1,1,1,1],
    [1,0,1,1,1,1,1,1,1,0,1],
    [1,0,1,0,0,0,0,0,1,0,1],
    [0,0,0,1,1,0,1,1,0,0,0],
    [0,0,1,0,0,0,0,0,1,0,0],
  ],
  react: [
    [0,0,0,1,1,1,1,1,0,0,0],
    [0,1,1,1,1,1,1,1,1,1,0],
    [1,1,0,1,1,1,1,1,0,1,1],
    [1,1,1,1,0,1,0,1,1,1,1],
    [0,1,1,1,1,1,1,1,1,1,0],
    [0,0,1,0,1,1,1,0,1,0,0],
    [0,1,0,1,0,0,0,1,0,1,0],
    [0,0,1,0,0,0,0,0,1,0,0],
  ],
  backend: [
    [0,0,1,1,0,0,0,1,1,0,0],
    [0,0,0,1,1,1,1,1,0,0,0],
    [0,1,1,1,1,1,1,1,1,1,0],
    [1,1,0,1,1,0,1,1,0,1,1],
    [1,1,1,1,1,1,1,1,1,1,1],
    [0,0,1,1,1,1,1,1,1,0,0],
    [0,1,1,0,0,0,0,0,1,1,0],
    [1,0,0,0,0,0,0,0,0,0,1],
  ],
  doc: [
    [0,0,1,1,1,1,1,1,1,0,0],
    [0,1,1,0,0,0,0,0,1,1,0],
    [1,1,0,1,1,1,1,1,0,1,1],
    [1,0,1,0,1,1,1,0,1,0,1],
    [1,0,1,1,1,1,1,1,1,0,1],
    [1,1,0,0,0,0,0,0,0,1,1],
    [0,1,1,1,0,0,0,1,1,1,0],
    [0,0,1,0,0,0,0,0,1,0,0],
  ],
  data: [
    [0,0,0,0,1,1,1,0,0,0,0],
    [0,0,0,1,1,1,1,1,0,0,0],
    [0,0,1,1,0,1,0,1,1,0,0],
    [0,1,1,0,1,1,1,0,1,1,0],
    [1,1,0,0,1,1,1,0,0,1,1],
    [1,0,0,1,1,1,1,1,0,0,1],
    [0,0,1,1,0,1,0,1,1,0,0],
    [0,1,1,0,0,0,0,0,1,1,0],
  ],
  orchestrator: [
    [1,0,0,1,0,0,0,1,0,0,1],
    [1,1,0,1,1,1,1,1,0,1,1],
    [1,1,1,1,1,1,1,1,1,1,1],
    [1,1,0,1,1,1,1,1,0,1,1],
    [0,1,1,1,1,1,1,1,1,1,0],
    [0,0,1,0,1,1,1,0,1,0,0],
    [0,1,0,1,0,0,0,1,0,1,0],
    [1,0,0,0,0,0,0,0,0,0,1],
  ],
};

function pickSprite(agentName) {
  const n = (agentName || '').toLowerCase();
  if (n.includes('orchestrat')) return 'orchestrator';
  if (n.includes('react') || n.includes('front') || n.includes('ui')) return 'react';
  if (n.includes('backend') || n.includes('server') || n.includes('api') || n.includes('engineer')) return 'backend';
  if (n.includes('doc') || n.includes('author')) return 'doc';
  if (n.includes('data') || n.includes('shape') || n.includes('keeper')) return 'data';
  return 'main';
}

function pickAgentColor(agentName) {
  const n = (agentName || '').toLowerCase();
  if (n.includes('orchestrat')) return 'var(--txt-bright)';
  if (n.includes('react') || n.includes('front') || n.includes('ui')) return 'var(--cyan)';
  if (n.includes('backend') || n.includes('server') || n.includes('api') || n.includes('engineer')) return 'var(--green)';
  if (n.includes('doc') || n.includes('author')) return 'var(--purple)';
  if (n.includes('data') || n.includes('shape') || n.includes('keeper')) return 'var(--gold)';
  return 'var(--cyan)';
}

const TOOL_COLORS = {
  Read: 'var(--cyan)', Edit: 'var(--gold)', Write: 'var(--gold)',
  Bash: 'var(--green)', Task: 'var(--purple)', Agent: 'var(--purple)',
  Glob: 'var(--teal)', Grep: 'var(--teal)', WebFetch: 'var(--orange)',
  WebSearch: 'var(--orange)',
};

const TOOL_ICONS = {
  Read: '◈', Edit: '✎', Write: '✎', Bash: '❯', Task: '◆',
  Agent: '◆', Glob: '⊛', Grep: '⊛', WebFetch: '⊕', WebSearch: '⊕',
};

function toolColor(t) { return TOOL_COLORS[t] || 'var(--muted)'; }
function toolIcon(t)  { return TOOL_ICONS[t] || '○'; }

function truncTarget(target) {
  if (!target) return '';
  const base = target.split('/').pop();
  if (base.length <= 14) return base;
  const dot = base.lastIndexOf('.');
  if (dot > 0 && base.length - dot <= 5) {   // has a short extension
    const ext = base.slice(dot);              // e.g. ".tsx"
    return base.slice(0, 11 - ext.length) + '…' + ext;
  }
  return base.slice(0, 13) + '…';
}

// ── SVG primitives ────────────────────────────────────────────────────────────

function PixelSprite({ x, y, sprite, color, px = 3 }) {
  const grid = SPRITES[sprite] || SPRITES.main;
  const cols = grid[0].length;
  const rows = grid.length;
  const ox = x - (cols * px) / 2;
  const oy = y - (rows * px) / 2;
  return (
    <g>
      {grid.map((row, ri) =>
        row.map((cell, ci) =>
          cell ? (
            <rect
              key={`${ri}-${ci}`}
              x={ox + ci * px} y={oy + ri * px}
              width={px - 0.5} height={px - 0.5}
              fill={color}
            />
          ) : null
        )
      )}
    </g>
  );
}

function CenterNode({ cx, cy, agentEntry, color, sprite }) {
  const r = 46;
  const active = agentEntry.secondsSinceLastEvent <= 8;
  const label = agentEntry.agent || 'main';
  return (
    <g>
      {/* Glow rings */}
      <circle cx={cx} cy={cy} r={r + 16} fill="none" stroke={color} strokeWidth={0.5} strokeOpacity={0.12} />
      <circle cx={cx} cy={cy} r={r + 8}  fill="none" stroke={color} strokeWidth={0.8} strokeOpacity={0.18} className={active ? 'lg-ring-pulse' : ''} />
      {/* BG */}
      <circle cx={cx} cy={cy} r={r} fill="var(--code-bg)" stroke={color} strokeWidth={1.5} />
      {/* Pixel sprite */}
      <PixelSprite x={cx} y={cy - 6} sprite={sprite} color={color} px={4} />
      {/* Agent name */}
      <text x={cx} y={cy + r - 9} textAnchor="middle" fontSize={7.5} fill={color} fontFamily="var(--font)" letterSpacing="0.04em">
        {label.length > 14 ? label.slice(0, 12) + '…' : label}
      </text>
      {/* Status pill */}
      <rect x={cx - 22} y={cy + r + 4} width={44} height={14} rx={7} fill={color} fillOpacity={0.14} stroke={color} strokeWidth={0.7} strokeOpacity={0.4} />
      <circle cx={cx - 11} cy={cy + r + 11} r={2.5} fill={active ? 'var(--live)' : 'var(--muted)'} />
      <text x={cx + 3} y={cy + r + 14} textAnchor="middle" fontSize={6.5} fill={active ? 'var(--live)' : 'var(--muted)'} fontFamily="var(--font)">
        {active ? 'ACTIVE' : 'IDLE'}
      </text>
    </g>
  );
}

function SatNode({ x, y, label, sublabel, color, icon, isHot }) {
  const r = 20;
  return (
    <g className={'lg-sat' + (isHot ? ' lg-sat-hot' : '')}>
      <circle cx={x} cy={y} r={r} fill="var(--code-bg)" stroke={color} strokeWidth={isHot ? 1.8 : 1.2} strokeOpacity={isHot ? 0.9 : 0.55} />
      {isHot && <circle cx={x} cy={y} r={r + 5} fill="none" stroke={color} strokeWidth={0.6} strokeOpacity={0.3} />}
      <text x={x} y={y + 1} textAnchor="middle" dominantBaseline="middle" fontSize={11} fill={color} opacity={isHot ? 1 : 0.75}>{icon}</text>
      <text x={x} y={y + r + 8} textAnchor="middle" fontSize={6.5} fill="var(--txt-bright)" fontFamily="var(--font)">{label}</text>
      {sublabel && (
        <text x={x} y={y + r + 17} textAnchor="middle" fontSize={5.5} fill="var(--muted)" fontFamily="var(--font)">{sublabel}</text>
      )}
    </g>
  );
}

function PulseLine({ x1, y1, x2, y2, color, active }) {
  return (
    <line
      x1={x1} y1={y1} x2={x2} y2={y2}
      stroke={color}
      strokeWidth={active ? 1.2 : 0.8}
      strokeOpacity={active ? 0.55 : 0.25}
      strokeDasharray="5 5"
      className={active ? 'lg-line-pulse' : ''}
    />
  );
}

// ── Main radial graph for one active agent ────────────────────────────────────

function AgentRadialGraph({ agentEntry, events, repo }) {
  const color = pickAgentColor(agentEntry.agent);
  const sprite = pickSprite(agentEntry.agent);
  const cx = 300, cy = 215;
  const radius = 155;

  const currentTool = agentEntry.currentTool || '';

  // Build satellite nodes from recent tool events (most recent unique tools)
  const toolEvents = events.filter(e => e.kind === 'tool' && e.tool);
  const seen = new Set();
  const uniqueTools = [];
  for (let i = toolEvents.length - 1; i >= 0 && uniqueTools.length < 5; i--) {
    const e = toolEvents[i];
    if (!seen.has(e.tool)) {
      seen.add(e.tool);
      uniqueTools.push({ ...e, isHot: e.tool === currentTool });
    }
  }

  // Deduplicated delegate / skill nodes (most-recent unique per agent/skill name)
  const specialSeen = new Set();
  const specialNodes = [];
  for (let i = events.length - 1; i >= 0 && specialNodes.length < 3; i--) {
    const e = events[i];
    if (e.kind === 'delegate' && e.to && !specialSeen.has('d:' + e.to)) {
      specialSeen.add('d:' + e.to);
      specialNodes.push({ tool: e.to, kind2: 'delegate' });
    } else if (e.kind === 'skill' && e.skill && !specialSeen.has('s:' + e.skill)) {
      specialSeen.add('s:' + e.skill);
      specialNodes.push({ tool: e.skill, kind2: 'skill' });
    }
  }

  const allNodes = [
    ...uniqueTools.map(e => ({
      label: e.tool,
      sublabel: truncTarget(e.target),
      color: toolColor(e.tool),
      icon: toolIcon(e.tool),
      isHot: e.isHot,
    })),
    ...specialNodes.map(n => ({
      label: n.tool.length > 14 ? n.tool.slice(0, 12) + '…' : n.tool,
      sublabel: n.kind2 === 'skill' ? 'skill' : 'sub-agent',
      color: n.kind2 === 'skill' ? 'var(--gold)' : 'var(--purple)',
      icon: n.kind2 === 'skill' ? '✦' : '◆',
      isHot: false,
    })),
  ];

  // Fall back to static repo skills/agents when there are no events
  if (allNodes.length === 0) {
    const fallback = [
      ...(repo.skills || []).slice(0, 4).map(s => ({ label: s, sublabel: 'skill', color: 'var(--gold)', icon: '✦', isHot: false })),
      ...(repo.commands || []).slice(0, 3).map(c => ({ label: c, sublabel: 'cmd', color: 'var(--teal)', icon: '⌘', isHot: false })),
    ];
    allNodes.push(...fallback.slice(0, 6));
  }

  const nodes = allNodes.slice(0, 7).map((n, i) => {
    const total = allNodes.slice(0, 7).length;
    const angle = (i / total) * 2 * Math.PI - Math.PI / 2;
    return { ...n, x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
  });

  // Elapsed display
  const elapsed = agentEntry.elapsedSec || 0;
  const elapsedStr = elapsed < 60 ? `${elapsed}s` : elapsed < 3600 ? `${Math.floor(elapsed / 60)}m` : `${Math.floor(elapsed / 3600)}h ${Math.floor((elapsed % 3600) / 60)}m`;

  return (
    <svg viewBox="0 0 600 430" className="lg-svg">
      <defs>
        <pattern id="lg-hex" x="0" y="0" width="30" height="17.3" patternUnits="userSpaceOnUse">
          <path d="M15 1 L29 9 L15 17 L1 9 Z" fill="none" stroke="var(--brd2)" strokeWidth="0.7" />
        </pattern>
        <radialGradient id="lg-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={color} stopOpacity="0.07" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Hex grid background */}
      <rect width="600" height="430" fill="url(#lg-hex)" rx="8" />
      {/* Radial glow behind center */}
      <circle cx={cx} cy={cy} r="190" fill="url(#lg-glow)" />

      {/* Pulse lines center → satellites */}
      {nodes.map((n, i) => (
        <PulseLine key={i} x1={cx} y1={cy} x2={n.x} y2={n.y} color={n.color} active={n.isHot} />
      ))}

      {/* Satellite nodes */}
      {nodes.map((n, i) => (
        <SatNode key={i} {...n} />
      ))}

      {/* Center agent node */}
      <CenterNode cx={cx} cy={cy} agentEntry={agentEntry} color={color} sprite={sprite} />

      {/* Info strip — current tool + elapsed time */}
      {currentTool && (
        <g transform="translate(300, 390)">
          <rect x="-105" y="-11" width="210" height="20" rx="5" fill="var(--code-bg)" stroke="var(--brd2)" strokeWidth="0.8" />
          <text x="0" y="3" textAnchor="middle" fontSize="8" fill={toolColor(currentTool)} fontFamily="var(--font)">
            {toolIcon(currentTool)}{' '}{currentTool}
            {agentEntry.currentTarget ? `  ·  ${truncTarget(agentEntry.currentTarget)}` : ''}
            {`  ·  ${elapsedStr} elapsed`}
          </text>
        </g>
      )}
    </svg>
  );
}

// ── Idle state: grid of all repo agents with pixel sprites ────────────────────

function IdleGrid({ repo }) {
  const agents = (repo.agents || []).slice(0, 8);
  if (agents.length === 0) {
    return (
      <div className="lg-idle-empty">
        <div className="lg-idle-icon">◈</div>
        <div className="lg-idle-label">No agents configured</div>
        <div className="lg-idle-sub">Define agents in .claude/agents/ to see them here</div>
      </div>
    );
  }
  return (
    <div className="lg-idle-grid">
      {agents.map(a => {
        const color = pickAgentColor(a);
        const sprite = pickSprite(a);
        const grid = SPRITES[sprite] || SPRITES.main;
        const px = 3, cols = grid[0].length, rows = grid.length;
        const sw = cols * px + 2, sh = rows * px + 2;
        return (
          <div key={a} className="lg-idle-card">
            <svg width={sw} height={sh} viewBox={`0 0 ${sw} ${sh}`}>
              {grid.map((row, ri) =>
                row.map((cell, ci) =>
                  cell ? (
                    <rect
                      key={`${ri}-${ci}`}
                      x={1 + ci * px} y={1 + ri * px}
                      width={px - 0.5} height={px - 0.5}
                      fill={color}
                    />
                  ) : null
                )
              )}
            </svg>
            <span className="lg-idle-name">{a}</span>
            <span className="lg-idle-status">idle</span>
          </div>
        );
      })}
    </div>
  );
}

// ── Public component ──────────────────────────────────────────────────────────

export default function LiveGraph({ repo, agents = [] }) {
  const events = useRepoEvents(repo.id, 80, 3000);
  const repoAgents = agents.filter(a => a.repo === repo.id);

  return (
    <div className="lg-wrap">
      {repoAgents.length === 0 ? (
        <div className="lg-idle">
          <div className="lg-idle-header">
            <span className="lg-idle-dot" />
            <span className="lg-idle-title">Monitoring · no active session</span>
          </div>
          <IdleGrid repo={repo} />
        </div>
      ) : (
        repoAgents.map(a => (
          <div key={a.sessionId} className="lg-session">
            <AgentRadialGraph agentEntry={a} events={events} repo={repo} />
          </div>
        ))
      )}
    </div>
  );
}
