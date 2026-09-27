import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAgents, useFileSizes } from "../api";
// Control rail removed per user feedback -- the graph runs on these tuned defaults.
const CONTROL_DEFAULTS = {
  glow: .75, fog: .5, cometFlow: .55, nodeSize: 1,
  linkOpacity: .5, linkDistance: 1, repulsion: 1,
  crossLinks: true, labels: false, colorBy: "kind", search: "",
};
import { SPRITES } from "./sprites";
import LiveAgents from "./LiveAgents";

// Layout constants: a fixed logical space the sim runs in. The camera
// pans/zooms this space into whatever pixel size the canvas actually is.
const LOGICAL_W = 900, LOGICAL_H = 540;
const CLUSTER_KINDS = ["agent", "skill", "command", "rule"];
const CLUSTER_RADIUS = Math.min(LOGICAL_W, LOGICAL_H) * 0.33;
const CLUSTER_ANCHORS = CLUSTER_KINDS.reduce((acc, kind, i) => {
  const ang = -Math.PI / 2 + i * (Math.PI / 2);
  acc[kind] = {
    x: LOGICAL_W / 2 + Math.cos(ang) * CLUSTER_RADIUS,
    y: LOGICAL_H / 2 + Math.sin(ang) * CLUSTER_RADIUS,
  };
  return acc;
}, {});
const KIND_ROLE = { agent: "cyan", skill: "gold", command: "green", rule: "purple" };
// Layer chip metadata for the internal (uncontrolled) chip row: layers.js key,
// display label, swatch color -- mirrors Graph.jsx chips but uses KIND_ROLE colors.
const LAYER_CHIPS = [
  { key: "agents", label: "agents", color: "cyan" },
  { key: "skills", label: "skills", color: "gold" },
  { key: "commands", label: "commands", color: "green" },
  { key: "rules", label: "rules", color: "purple" },
];
const KIND_GLYPH = { agent: "◆", skill: "✦", command: "❯", rule: "§" };
// Tree topology: each category hub is a real pinned "leaf robot" with its own sprite.
const LEAF_SPRITE = { agent: "orchestrator", skill: "data", command: "backend", rule: "doc" };
const LEAF_R = 20;
const LAYER_FOR_KIND = { agent: "agents", skill: "skills", command: "commands", rule: "rules" };
const REST_LEN = { owns: 115, uses: 170, entry: 230, context: 210, delegate: 160, ephemeral: 55, trunk: 178 };
// uses/delegate are semantic cross-links -- near-zero spring so they draw a
// relationship without dragging agents out of their leaf family.
const SPRING_K = { entry: 0.025, context: 0.025, ephemeral: 0.02, uses: 0.004, delegate: 0.006 };
const DEFAULT_SPRING_K = 0.04;
const STAR_COUNT = 120;
const COMET_CAP = 60;
const COMET_SPEED = 0.008;
const ENERGY_SLEEP_THRESHOLD = 0.15;
const SLEEP_FRAMES = 60;
// Phase 2 live-plane constants.
const EPHEMERAL_TTL_MS = 30000;
const TOOL_SATELLITE_TTL_MS = 12000;
const EPHEMERAL_FADE_MS = 5000;
const LIVE_RING_PAD = 6;
const LIVE_RING_AMPLITUDE = 3;
const LIVE_ACTIVE_WINDOW_SEC = 8;
// Phase 3 permanent-sprite constants.
const AGENT_DISC_MIN_R = 13;
const MEMBER_DISC_MIN_R = 11;
const SPRITE_SIZE_RATIO = 1.35;
const LOD_SPRITE_MIN_PX = 9;

// Pure helpers (no React, no refs).

function sizeFor(FILE_SIZES, kind, name, fallbackBytes) {
  const bytes = FILE_SIZES[kind + "s"]?.[name] ?? fallbackBytes;
  const k = Math.sqrt(Math.max(0.2, bytes / 1000));
  const ranges = {
    agent: [4, 11, 3.0], skill: [3.5, 10, 2.8], command: [3, 7, 2.0], rule: [3, 8, 2.2],
  };
  const [lo, hi, mult] = ranges[kind] || [10, 18, 5];
  return { r: Math.max(lo, Math.min(hi, lo + k * mult)), bytes };
}

// Node/edge assembly, ported from the useMemo body in Graph.jsx.
function buildGraph(repo, layers, agentMeta, FILE_SIZES) {
  if (!repo) return { nodes: [], edges: [] };
  const cx = LOGICAL_W / 2, cy = LOGICAL_H / 2;
  const nodes = [{ id: "__repo__", label: repo.name, kind: "repo", r: 34, color: repo.accent, x: cx, y: cy, fx: cx, fy: cy }];

  const skillAgents = (skill) => {
    const tokens = skill.toLowerCase().split("-");
    return repo.agents.filter(a => tokens.some(t => a.toLowerCase().includes(t) && t.length > 3));
  };

  if (layers.agents) {
    repo.agents.forEach((a, i) => {
      const calls = agentMeta[a]?.callsToday ?? 1;
      const { r, bytes } = sizeFor(FILE_SIZES, "agent", a, 3000);
      const ang = (i / repo.agents.length) * Math.PI * 2 - Math.PI / 2;
      nodes.push({
        id: "a-" + a, label: a, kind: "agent", color: "cyan", r,
        x: cx + Math.cos(ang) * 160, y: cy + Math.sin(ang) * 160,
        meta: { callsToday: calls, bytes },
      });
    });
  }
  if (layers.skills) {
    repo.skills.forEach((s, i) => {
      const matches = skillAgents(s).length;
      const { r, bytes } = sizeFor(FILE_SIZES, "skill", s, 4000);
      const ang = (i / repo.skills.length) * Math.PI * 2 - Math.PI / 2 + (Math.PI / repo.skills.length);
      nodes.push({
        id: "s-" + s, label: s, kind: "skill", color: "gold", r,
        x: cx + Math.cos(ang) * 250, y: cy + Math.sin(ang) * 250,
        meta: { usedBy: matches, bytes },
      });
    });
  }
  if (layers.commands) {
    (repo.commands || []).forEach((c, i) => {
      const { r, bytes } = sizeFor(FILE_SIZES, "command", c, 800);
      const ang = (i / Math.max(1, (repo.commands || []).length)) * Math.PI * 2 + Math.PI / 6;
      nodes.push({
        id: "c-" + c, label: c, kind: "command", color: "green", r,
        x: cx + Math.cos(ang) * 320, y: cy + Math.sin(ang) * 200,
        meta: { bytes },
      });
    });
  }
  if (layers.rules) {
    (repo.rules || []).forEach((rl, i) => {
      const { r, bytes } = sizeFor(FILE_SIZES, "rule", rl, 1500);
      const ang = (i / Math.max(1, (repo.rules || []).length)) * Math.PI * 2 - Math.PI / 3;
      nodes.push({
        id: "r-" + rl, label: rl, kind: "rule", color: "purple", r,
        x: cx + Math.cos(ang) * 290, y: cy + Math.sin(ang) * 220,
        meta: { bytes },
      });
    });
  }

  const edges = [];
  // Tree: repo robot -> 4 leaf robots (pinned at anchors) -> their members.
  CLUSTER_KINDS.forEach(kind => {
    if (!layers[LAYER_FOR_KIND[kind]]) return;
    const a = CLUSTER_ANCHORS[kind];
    nodes.push({
      id: "leaf-" + kind, label: kind + "s", kind: "leaf", leafKind: kind,
      color: KIND_ROLE[kind], r: LEAF_R, x: a.x, y: a.y, fx: a.x, fy: a.y,
    });
    edges.push({ from: "__repo__", to: "leaf-" + kind, kind: "trunk" });
  });
  if (layers.agents) {
    repo.agents.forEach(a => edges.push({ from: "leaf-agent", to: "a-" + a, kind: "owns" }));
    repo.agents.forEach(a => {
      (agentMeta[a]?.delegates || []).forEach(d => {
        if (repo.agents.includes(d)) edges.push({ from: "a-" + a, to: "a-" + d, kind: "delegate" });
      });
    });
  }
  if (layers.skills) {
    repo.skills.forEach(s => {
      const matches = skillAgents(s);
      edges.push({ from: "leaf-skill", to: "s-" + s, kind: "owns" });
      if (matches.length && layers.agents) edges.push({ from: "a-" + matches[0], to: "s-" + s, kind: "uses" });

    });
  }
  if (layers.commands) (repo.commands || []).forEach(c => edges.push({ from: "leaf-command", to: "c-" + c, kind: "owns" }));
  if (layers.rules) (repo.rules || []).forEach(rl => edges.push({ from: "leaf-rule", to: "r-" + rl, kind: "owns" }));

  return { nodes, edges };
}

// Resolve {from,to} id-edges into {a,b} object refs once per rebuild so sim
// and draw never do an id lookup per tick or frame.
function resolveEdges(nodes, edges) {
  const byId = new Map(nodes.map(n => [n.id, n]));
  const resolved = [];
  edges.forEach(e => {
    const a = byId.get(e.from), b = byId.get(e.to);
    if (a && b) resolved.push({ kind: e.kind, a, b });
  });
  return resolved;
}

// Force step: repulsion, springs and center pull ported from Graph.jsx, plus
// a per-kind cluster-anchor pull that is new to Nebula. Returns total kinetic
// energy so the caller can detect rest and stop ticking.
function simTick(nodes, resolvedEdges, controls) {
  const repulseK = 2200 * controls.repulsion;
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j];
      let dx = b.x - a.x, dy = b.y - a.y;
      let d2 = dx * dx + dy * dy;
      if (d2 < 1) { d2 = 1; dx = .5; dy = .5; }
      const d = Math.sqrt(d2);
      const f = repulseK / d2;
      const fx = (dx / d) * f, fy = (dy / d) * f;
      if (a.fx == null) { a.vx -= fx; a.vy -= fy; }
      if (b.fx == null) { b.vx += fx; b.vy += fy; }
    }
  }

  resolvedEdges.forEach(e => {
    const a = e.a, b = e.b;
    const dx = b.x - a.x, dy = b.y - a.y;
    const d = Math.sqrt(dx * dx + dy * dy) || .001;
    const rest = (REST_LEN[e.kind] ?? 150) * controls.linkDistance;
    const k = SPRING_K[e.kind] ?? DEFAULT_SPRING_K;
    const f = (d - rest) * k;
    const fx = (dx / d) * f, fy = (dy / d) * f;
    if (a.fx == null) { a.vx += fx; a.vy += fy; }
    if (b.fx == null) { b.vx -= fx; b.vy -= fy; }
  });

  // Members gravitate toward their LEAF ROBOT (live position -- so dragging a
  // leaf takes its family along), falling back to the static anchor.
  const leafPos = {};
  nodes.forEach(n => { if (n.kind === "leaf") leafPos[n.leafKind] = n; });
  nodes.forEach(n => {
    if (n.fx != null) return;
    const anchor = leafPos[n.kind] || CLUSTER_ANCHORS[n.kind];
    if (anchor) {
      // Family gravity replaces center pull -- pulling both ways just smears
      // members along the leaf-center axis.
      n.vx += (anchor.x - n.x) * 0.004;
      n.vy += (anchor.y - n.y) * 0.004;
    } else {
      n.vx += (LOGICAL_W / 2 - n.x) * 0.0015;
      n.vy += (LOGICAL_H / 2 - n.y) * 0.0015;
    }
  });

  let energy = 0;
  nodes.forEach(n => {
    if (n.fx != null) { n.x = n.fx; n.y = n.fy; n.vx = 0; n.vy = 0; return; }
    n.vx *= 0.85; n.vy *= 0.85;
    n.x += n.vx; n.y += n.vy;
    if (!Number.isFinite(n.x) || !Number.isFinite(n.y) || Math.abs(n.x) > 50000 || Math.abs(n.y) > 50000) {
      const anchor = CLUSTER_ANCHORS[n.kind] || { x: LOGICAL_W / 2, y: LOGICAL_H / 2 };
      n.x = anchor.x; n.y = anchor.y; n.vx = 0; n.vy = 0;
    }
    const m = n.r + 30;
    if (n.x < m) { n.x = m; n.vx *= -.4; }
    if (n.x > LOGICAL_W - m) { n.x = LOGICAL_W - m; n.vx *= -.4; }
    if (n.y < m) { n.y = m; n.vy *= -.4; }
    if (n.y > LOGICAL_H - m) { n.y = LOGICAL_H - m; n.vy *= -.4; }
    energy += n.vx * n.vx + n.vy * n.vy;
  });
  return energy;
}

function readRoleColors(dark) {
  const cs = getComputedStyle(document.body);
  const get = (name, fallback) => cs.getPropertyValue(name).trim() || fallback;
  return {
    // Light repurposes --cyan AND --gold to ambers, which makes the agents and
    // skills families near-identical on the graph. A graph is a chart, and the
    // dual-theme rule reserves pure cool blue for charts -- so in light the
    // agents family takes a chart blue instead of the amber token.
    cyan: dark ? get("--cyan", "#06b6d4") : "#0284c7",
    gold: get("--gold", "#FFC107"),
    green: get("--green", "#10b981"),
    purple: get("--purple", "#a78bfa"),
    txt: get("--txt", "#94a3b8"),
    txtBright: get("--txt-bright", "#e2e8f0"),
    rose: get("--rose", "#f472b6"),
    live: get("--live", "#00ff88"),
    bg2: get("--bg2", "#0d1322"),
  };
}

function resolveColor(colorField, roleColors) {
  if (!colorField) return roleColors.txt;
  if (colorField[0] === "#") return colorField;
  return roleColors[colorField] || colorField;
}

function hexToRgba(hex, a) {
  let h = (hex || "").trim().replace("#", "");
  if (h.length === 3) h = h.split("").map(c => c + c).join("");
  const n = parseInt(h, 16);
  if (Number.isNaN(n)) return `rgba(6,182,212,${a})`;
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

function buildStars(count) {
  const stars = [];
  for (let i = 0; i < count; i++) {
    stars.push({
      xf: Math.random(), yf: Math.random(),
      r: Math.random() * 1 + 0.4,
      a: Math.random() * 0.45 + 0.15,
    });
  }
  return stars;
}

function edgeControlPoint(a, b) {
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
  const dx = b.x - a.x, dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len, ny = dx / len;
  const bow = len * 0.08;
  return { x: mx + nx * bow, y: my + ny * bow };
}

function quadPoint(a, ctrl, b, t) {
  const mt = 1 - t;
  return { x: mt * mt * a.x + 2 * mt * t * ctrl.x + t * t * b.x, y: mt * mt * a.y + 2 * mt * t * ctrl.y + t * t * b.y };
}

function hitTestNode(nodes, wx, wy) {
  let best = null, bestD = Infinity;
  for (const n of nodes) {
    const d = Math.hypot(n.x - wx, n.y - wy);
    if (d <= n.r + 6 && d < bestD) { best = n; bestD = d; }
  }
  return best;
}

function hitTestClusterAnchor(wx, wy) {
  for (const kind of CLUSTER_KINDS) {
    const a = CLUSTER_ANCHORS[kind];
    if (Math.hypot(a.x - wx, a.y - wy) <= 20) return kind;
  }
  return null;
}

function fitCam(cssW, cssH) {
  const scale = Math.min(cssW / LOGICAL_W, cssH / LOGICAL_H) * 0.92;
  return { x: cssW / 2 - (LOGICAL_W / 2) * scale, y: cssH / 2 - (LOGICAL_H / 2) * scale, scale };
}

function fitCamToPoint(cssW, cssH, px, py, scale) {
  return { x: cssW / 2 - px * scale, y: cssH / 2 - py * scale, scale };
}

function trySpawnComet(comets, visibleEdges) {
  if (comets.length >= COMET_CAP || !visibleEdges.length) return;
  const e = visibleEdges[Math.floor(Math.random() * visibleEdges.length)];
  comets.push({ a: e.a, b: e.b, progress: 0 });
}

function updateComets(comets) {
  for (let i = comets.length - 1; i >= 0; i--) {
    comets[i].progress += COMET_SPEED;
    if (comets[i].progress >= 1) comets.splice(i, 1);
  }
}

// -- Phase 2: live-plane pure helpers -------------------------------------

// Resolves a "var(--token)" string against
// the role colors read above, falling back to a fresh getComputedStyle read
// for tokens not already captured there.
function resolveVarColor(varStr, roleColors) {
  const m = /var\(--([\w-]+)\)/.exec(varStr || "");
  if (!m) return varStr || roleColors.txt;
  const key = m[1].replace(/-([a-z])/g, (_, c) => c.toUpperCase());
  if (roleColors[key]) return roleColors[key];
  const cs = getComputedStyle(document.body);
  return cs.getPropertyValue("--" + m[1]).trim() || roleColors.txt;
}

function hashSeed(id) {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 1000;
  return (h / 1000) * Math.PI * 2;
}

// "main" (or any agent name with no matching structural node) maps to the
// repo hub; a named sub-agent maps to its own node when the layer is on.
function resolveAgentNode(agentName, nodes) {
  const hub = nodes.find(n => n.id === "__repo__");
  if (!agentName || agentName === "main") return hub;
  return nodes.find(n => n.id === "a-" + agentName) || hub;
}

function resolveEventActor(sessionId, nodes, liveRows) {
  if (sessionId) {
    const row = liveRows.find(r => r.sessionId === sessionId);
    if (row) return resolveAgentNode(row.agent, nodes);
  }
  return resolveAgentNode(null, nodes);
}

// Live rows keyed by the structural node they resolve to, so the draw pass
// can look up "does this node have an active session" in O(1).
function groupLiveRows(rows, nodes) {
  const groups = new Map();
  rows.forEach(row => {
    const node = resolveAgentNode(row.agent, nodes);
    if (!node) return;
    if (!groups.has(node.id)) groups.set(node.id, { node, rows: [] });
    groups.get(node.id).rows.push(row);
  });
  return groups;
}

function ephemeralFade(n, now) {
  const ttl = n.subKind === "tool" ? TOOL_SATELLITE_TTL_MS : EPHEMERAL_TTL_MS;
  const age = now - n.born;
  const fadeStart = ttl - EPHEMERAL_FADE_MS;
  if (age <= fadeStart) return 1;
  return Math.max(0, 1 - (age - fadeStart) / (ttl - fadeStart));
}

// Ephemeral nodes stand in for delegate/skill/command targets (and tool
// satellites) with no structural counterpart. They join nodes/edges
// directly so sim + draw handle them for free via the ephemeral spring.
function getOrCreateEphemeral(subKind, label, spawner, nodes, edges, index, now, roleColors) {
  const key = subKind + ":" + label;
  const existing = index.get(key);
  if (existing) {
    existing.born = now;
    return existing;
  }
  const colorVar = subKind === "skill" ? "var(--gold)"
    : subKind === "command" ? "var(--green)"
    : subKind === "tool" ? "var(--muted)"
    : "var(--purple)";
  const angle = Math.random() * Math.PI * 2;
  const dist = subKind === "tool" ? 26 : 42;
  const node = {
    id: "eph-" + subKind + "-" + label + "-" + Math.random().toString(36).slice(2, 7),
    label, kind: "ephemeral", subKind,
    r: subKind === "tool" ? 5 : 6,
    color: resolveVarColor(colorVar, roleColors),
    x: spawner.x + Math.cos(angle) * dist,
    y: spawner.y + Math.sin(angle) * dist,
    vx: 0, vy: 0,
    born: now,
  };
  nodes.push(node);
  edges.push({ kind: "ephemeral", a: spawner, b: node });
  index.set(key, node);
  return node;
}

function pruneEphemerals(nodes, edges, index, now) {
  const dead = new Set();
  for (let i = nodes.length - 1; i >= 0; i--) {
    const n = nodes[i];
    if (n.kind !== "ephemeral") continue;
    const ttl = n.subKind === "tool" ? TOOL_SATELLITE_TTL_MS : EPHEMERAL_TTL_MS;
    if (now - n.born > ttl) { dead.add(n.id); nodes.splice(i, 1); }
  }
  if (!dead.size) return;
  for (let i = edges.length - 1; i >= 0; i--) {
    const e = edges[i];
    if (dead.has(e.a.id) || dead.has(e.b.id)) edges.splice(i, 1);
  }
  for (const [k, v] of index) if (dead.has(v.id)) index.delete(k);
}

// `id` alone is not a safe dedup key: /api/live/recent stamps it from the
// DB pk while /ws/live stamps it from the Hub seq (routers/live.py) --
// different numbering spaces that can collide. Key on payload identity.
function eventDedupKey(e) {
  const sid = e.sessionId || "";
  const stamp = e.ts || e.t;
  switch (e.kind) {
    case "tool": return "tool|" + e.repo + "|" + e.tool + "|" + e.target + "|" + stamp + "|" + sid;
    case "delegate": return "delegate|" + e.repo + "|" + e.from + "|" + e.to + "|" + stamp + "|" + sid;
    case "skill": return "skill|" + e.repo + "|" + e.skill + "|" + stamp + "|" + sid;
    case "command": return "command|" + e.repo + "|" + e.cmd + "|" + stamp + "|" + sid;
    default: return e.kind + "|" + e.repo + "|" + stamp + "|" + sid;
  }
}

function spawnLiveComet(comets, a, b, cap) {
  if (!a || !b || a === b) return;
  if (comets.length >= cap) comets.shift();
  comets.push({ a, b, progress: 0, live: true });
}

function liveRingRadius(baseR, now, seed, reducedMotion) {
  if (reducedMotion) return baseR + LIVE_RING_PAD;
  return baseR + LIVE_RING_PAD + Math.sin(now / 280 + seed) * LIVE_RING_AMPLITUDE;
}

function drawLiveRing(ctx, n, drawnR, group, ringColor, now, reducedMotion) {
  const active = group.rows.some(r => (r.secondsSinceLastEvent ?? 99) <= LIVE_ACTIVE_WINDOW_SEC);
  const ringR = liveRingRadius(drawnR, now, hashSeed(n.id), reducedMotion);
  ctx.beginPath();
  ctx.arc(n.x, n.y, ringR, 0, Math.PI * 2);
  ctx.strokeStyle = hexToRgba(ringColor, active ? 0.85 : 0.35);
  ctx.lineWidth = active ? 2.2 : 1.4;
  ctx.stroke();
}

// Shared sprite renderer for every permanent robo-disc (agent nodes + hub).
// Root cause of the oversized-sprite bug: the previous per-node draw derived
// cell size from drawnR * 3.2 (a multiple of that one node radius, uncapped)
// with no relation to the disc size, so the sprite footprint scaled directly
// off the physics radius instead of a fraction of it -- on larger nodes (the
// hub especially) it grew to several times the disc. This helper instead
// takes an explicit target size chosen by the caller as a fraction of the
// disc radius and fits the sprite grid inside it, centered.
function drawSprite(ctx, grid, cx, cy, size, color) {
  const cols = grid[0].length, rows = grid.length;
  const cell = size / cols;
  const ox = cx - size / 2;
  const oy = cy - (cell * rows) / 2;
  ctx.fillStyle = color;
  for (let ri = 0; ri < rows; ri++) {
    for (let ci = 0; ci < cols; ci++) {
      if (!grid[ri][ci]) continue;
      ctx.fillRect(ox + ci * cell, oy + ri * cell, cell - 0.3, cell - 0.3);
    }
  }
}

function drawLiveBadge(ctx, n, drawnR, count, badgeColor) {
  const bx = n.x + drawnR * 0.75, by = n.y - drawnR * 0.75;
  ctx.beginPath();
  ctx.arc(bx, by, 7, 0, Math.PI * 2);
  ctx.fillStyle = badgeColor;
  ctx.fill();
  ctx.fillStyle = "#00120a";
  ctx.font = "700 8px Fira Code, monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(String(count), bx, by + 0.5);
}

// Full render pass, in order: backdrop, cluster fog, edges, comets, nodes and
// cluster hubs, then labels. Reads theme and design tokens fresh every call
// so it stays reactive to theme toggles without any extra plumbing.
function draw(ctx, cssW, cssH, cam, nodes, resolvedEdges, controls, hoverId, comets, stars, theme, liveGroups, now, reducedMotion, themeCache) {
  const dark = theme !== "light";
  const { roleColors, gradients } = themeCache;
  ctx.clearRect(0, 0, cssW, cssH);

  if (dark) {
    stars.forEach(s => {
      ctx.beginPath();
      ctx.arc(s.xf * cssW, s.yf * cssH, s.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255,255,255,${s.a})`;
      ctx.fill();
    });
  }

  ctx.save();
  ctx.translate(cam.x, cam.y);
  ctx.scale(cam.scale, cam.scale);

  CLUSTER_KINDS.forEach(kind => {
    const anchor = CLUSTER_ANCHORS[kind];
    ctx.fillStyle = gradients[kind];
    ctx.beginPath();
    ctx.arc(anchor.x, anchor.y, 180, 0, Math.PI * 2);
    ctx.fill();
  });

  const visibleEdges = [];
  resolvedEdges.forEach(e => {
    if (!controls.crossLinks && (e.kind === "uses" || e.kind === "delegate")) return;
    visibleEdges.push(e);
    const active = hoverId && (hoverId === e.a.id || hoverId === e.b.id);
    const ctrl = edgeControlPoint(e.a, e.b);
    const color = resolveColor(e.a.color, roleColors);
    // Visual hierarchy: trunks (hub->leaf) strongest, family branches solid,
    // semantic cross-links a whisper.
    const baseAlpha = e.kind === "trunk" ? 0.6 : (e.kind === "owns" ? 0.42 : (e.kind === "uses" || e.kind === "delegate") ? 0.16 : 0.25);
    ctx.beginPath();
    ctx.moveTo(e.a.x, e.a.y);
    ctx.quadraticCurveTo(ctrl.x, ctrl.y, e.b.x, e.b.y);
    ctx.strokeStyle = hexToRgba(color, (active ? 0.7 : baseAlpha) * controls.linkOpacity);
    ctx.lineWidth = e.kind === "trunk" ? 1.6 : active ? 1.8 : 1;
    ctx.stroke();
  });


  comets.forEach(c => {
    const ctrl = edgeControlPoint(c.a, c.b);
    const color = resolveColor(c.a.color, roleColors);
    const baseAlpha = c.live ? 1 : 0.95;
    const spread = c.live ? 0.035 : 0.03;
    for (let k = 3; k >= 0; k--) {
      const t = c.progress - k * spread;
      if (t < 0 || t > 1) continue;
      const p = quadPoint(c.a, ctrl, c.b, t);
      const alpha = k === 0 ? baseAlpha : baseAlpha * (1 - k / (c.live ? 3.2 : 4));
      ctx.beginPath();
      ctx.arc(p.x, p.y, k === 0 ? (c.live ? 2.8 : 2.2) : (c.live ? 1.8 : 1.4), 0, Math.PI * 2);
      ctx.fillStyle = hexToRgba(color, alpha);
      ctx.fill();
    }
  });

  const scale = cam.scale;
  const viewMinX = -cam.x / scale, viewMinY = -cam.y / scale;
  const viewMaxX = viewMinX + cssW / scale, viewMaxY = viewMinY + cssH / scale;
  const q = controls.search ? controls.search.trim().toLowerCase() : "";

  // Permanent robo-disc rendering for agent + hub nodes: dark disc, colored
  // ring, pixel sprite centered inside -- always visible, not gated on a
  // live session. The live overlay (pulsing ring + badge) layers on top,
  // keyed by node.id via liveGroups.
  // Disc surface: --bg2 resolves per theme (deep navy in dark, warm cream in
  // light) so robots sit on an elevated surface native to each scheme.
  const discBg = roleColors.bg2;
  nodes.forEach(n => {
    const isHub = n.kind === "repo";
    const isAgent = n.kind === "agent";
    const isLeaf = n.kind === "leaf";
    const color = resolveColor(n.color, roleColors);
    // Own identity color -- reused for the sprite ring, the live pulse ring
    // and the live session badge, so a node's live accents always read as
    // *its* color rather than a shared green status color.
    // Family identity: minis copy their parental leaf robot -- same sprite,
    // same family color. EXCEPTIONS: special agents keep a personal identity
    // (orchestrators = white/grey classic invader, doc agents = rose doc-bot).
    let ownColor = color;
    let spriteOverride = null;
    if (n.kind === "agent") {
      const ln = n.label.toLowerCase();
      if (ln.includes("orchestrat")) { ownColor = roleColors.txtBright; spriteOverride = "main"; }
      else if (ln.includes("doc") || ln.includes("author")) { ownColor = roleColors.rose; spriteOverride = "doc"; }
    }
    let drawnR;
    if (isHub) drawnR = n.r;
    else if (isAgent) drawnR = Math.max(n.r, AGENT_DISC_MIN_R) * controls.nodeSize;
    else if (LEAF_SPRITE[n.kind]) drawnR = Math.max(n.r, MEMBER_DISC_MIN_R) * controls.nodeSize;
    else if (isLeaf) drawnR = n.r * (reducedMotion ? 1 : 1 + Math.sin(now / 500 + hashSeed(n.id)) * 0.06);
    else drawnR = n.r * controls.nodeSize;
    const matches = !q || n.label.toLowerCase().includes(q);
    const fade = n.kind === "ephemeral" ? ephemeralFade(n, now) : 1;
    ctx.globalAlpha = ((q && !matches) ? 0.25 : 1) * fade;

    const liveGroup = liveGroups.get(n.id);
    if (liveGroup) drawLiveRing(ctx, n, drawnR, liveGroup, ownColor, now, reducedMotion);

    const screenR = drawnR * scale;
    const showSprite = (isHub || isLeaf || !!LEAF_SPRITE[n.kind]) && screenR >= LOD_SPRITE_MIN_PX;
    // R-LAT-7: shadowBlur is one of the most expensive 2D canvas ops and was
    // previously set on every node every frame. Reserve it for nodes that
    // actually earn the attention -- hub, hovered, and nodes with a live
    // session -- everything else gets a flat (still colored) stroke/fill.
    const wantsGlow = isHub || n.id === hoverId || !!liveGroup;

    if (showSprite) {
      ctx.beginPath();
      ctx.arc(n.x, n.y, drawnR, 0, Math.PI * 2);
      ctx.fillStyle = discBg;
      ctx.fill();
      if (wantsGlow) {
        ctx.shadowBlur = (dark ? 12 : 4) * controls.glow;
        ctx.shadowColor = dark ? ownColor : hexToRgba(ownColor, 0.45);
      }
      ctx.lineWidth = dark ? 2 : 2.5;
      ctx.strokeStyle = ownColor;
      ctx.beginPath();
      ctx.arc(n.x, n.y, drawnR, 0, Math.PI * 2);
      ctx.stroke();
      ctx.shadowBlur = 0;
      if (isLeaf) {
        // Second, thinner outer ring -- marks category hubs as containers,
        // visually distinct from same-sprite member robots.
        ctx.beginPath();
        ctx.arc(n.x, n.y, drawnR + 4, 0, Math.PI * 2);
        ctx.lineWidth = 1;
        ctx.strokeStyle = hexToRgba(ownColor, 0.5);
        ctx.stroke();
      }
      const spriteName = isHub ? "main" : spriteOverride || LEAF_SPRITE[isLeaf ? n.leafKind : n.kind] || "main";
      const grid = SPRITES[spriteName] || SPRITES.main;
      drawSprite(ctx, grid, n.x, n.y, drawnR * SPRITE_SIZE_RATIO, ownColor);
    } else {
      if (wantsGlow) {
        ctx.shadowBlur = (dark ? 14 : 6) * controls.glow;
        ctx.shadowColor = color;
      }
      ctx.beginPath();
      ctx.arc(n.x, n.y, drawnR, 0, Math.PI * 2);
      ctx.fillStyle = hexToRgba(color, dark ? (isHub ? 0.9 : 0.8) : 0.75);
      ctx.fill();
      if (!dark) { ctx.lineWidth = 1; ctx.strokeStyle = "rgba(255,255,255,.85)"; ctx.stroke(); }
      ctx.shadowBlur = 0;
      ctx.fillStyle = "#fff";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      if (isHub) {
        ctx.font = "700 13px Fira Code, monospace";
        ctx.fillText(n.label, n.x, n.y);
      } else {
        ctx.font = `700 ${Math.max(8, drawnR * 0.9)}px Fira Code, monospace`;
        ctx.fillText(KIND_GLYPH[n.kind] || "", n.x, n.y);
      }
    }

    if (liveGroup && liveGroup.rows.length > 1) drawLiveBadge(ctx, n, drawnR, liveGroup.rows.length, ownColor);

    ctx.globalAlpha = 1;
  });


  ctx.font = "10px Fira Code, monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = roleColors.txt;
  nodes.forEach(n => {
    if (n.kind === "repo") return;
    const inViewport = n.x >= viewMinX && n.x <= viewMaxX && n.y >= viewMinY && n.y <= viewMaxY;
    const matches = !q || n.label.toLowerCase().includes(q);
    let shouldLabel;
    if (n.kind === "ephemeral") shouldLabel = true;
    else if (n.kind === "leaf") shouldLabel = true;
    else if (controls.labels) shouldLabel = true;
    else if (scale > 1.6) shouldLabel = inViewport;
    else shouldLabel = (n.id === hoverId) || (q && matches);
    if (!shouldLabel) return;
    ctx.globalAlpha = (q && !matches) ? 0.25 : 1;
    const label = n.label.length > 22 ? n.label.slice(0, 20) + "…" : n.label;
    ctx.fillText(label, n.x, n.y + n.r * controls.nodeSize + 12);
    ctx.globalAlpha = 1;
  });

  ctx.restore();
}

// R-LAT-4: liveEvents/liveAgents are owned by App's single app-wide poller/WS
// (useLiveEvents/useActiveAgents) and threaded down via Graph.jsx / RepoDetail.jsx.
// Don't reintroduce a second useActiveAgents(1.5s)/useLiveEvents() call here --
// that was a real duplicate poller, not just an inefficiency.
export default function NebulaGraph({ repos, lockedRepo, defaultLayers, onOpen, selectedRepo: controlledRepo, layers: controlledLayers, liveEvents = [], liveAgents = [] }) {
  // Selection is fully derived: locked (RepoDetail) > controlled (Graph page chips) > first repo.
  const selectedRepo = lockedRepo ?? controlledRepo ?? repos[0]?.id;
  const layersKey = JSON.stringify(defaultLayers ?? null);
  const fallbackLayers = useMemo(
    () => ({ agents: true, skills: true, commands: true, rules: true, ...defaultLayers }),
    // Keyed on CONTENT (layersKey), not identity: an inline defaultLayers={{...}}
    // prop would otherwise rebuild the whole sim every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [layersKey],
  );
  // When nobody controls layers (RepoDetail mount), NebulaGraph manages its
  // own toggle state and renders its own chip row above the canvas.
  const [internalLayers, setInternalLayers] = useState(null);
  const layers = controlledLayers ?? internalLayers ?? fallbackLayers;
  const controls = CONTROL_DEFAULTS;
  const [hoverLabel, setHoverLabel] = useState("");

  const { data: AGENT_META } = useAgents();
  const FILE_SIZES = useFileSizes();
  const repo = lockedRepo ? repos.find(r => r.id === lockedRepo) : (repos.find(r => r.id === selectedRepo) || repos[0]);
  const liveRows = liveAgents;

  const { nodes: builtNodes, edges: builtEdges } = useMemo(
    () => buildGraph(repo, layers, AGENT_META, FILE_SIZES),
    [repo, layers, AGENT_META, FILE_SIZES],
  );

  const repoLiveRows = useMemo(() => (repo ? liveRows.filter(r => r.repo === repo.id) : []), [liveRows, repo]);

  const wrapRef = useRef(null);
  const canvasRef = useRef(null);
  const nodesRef = useRef([]);
  const edgesRef = useRef([]);
  const camRef = useRef({ x: 0, y: 0, scale: 1 });
  const tweenRef = useRef(null);
  const cometsRef = useRef([]);
  const cometTimerRef = useRef(0);
  const starsRef = useRef(null);
  if (starsRef.current === null) starsRef.current = buildStars(STAR_COUNT);
  const hoverRef = useRef(null);
  const draggingRef = useRef(null);
  const kineticRef = useRef({ lowFrames: 0, sleeping: false });
  const sizeRef = useRef({ w: 0, h: 0 });
  const dprRef = useRef(1);
  const reducedMotionRef = useRef(false);
  const controlsRef = useRef(controls);
  const onOpenRef = useRef(onOpen);
  const drawNowRef = useRef(() => {});
  const liveRowsRef = useRef([]);
  const ephemeralIndexRef = useRef(new Map());
  const processedEventKeysRef = useRef(new Set());
  // R-LAT-7: cached role colors + cluster gradients, invalidated only on a
  // theme flip (see MutationObserver below) instead of rebuilt every frame.
  const themeCacheRef = useRef(null);
  // True while wrapRef's canvas is actually in the viewport (IntersectionObserver).
  const isVisibleRef = useRef(true);
  // Lets effects outside the main rAF-loop effect (liveEvents processing,
  // repo/layer rebuild, repoLiveRows sync) resume a parked loop without
  // duplicating the rAF-scheduling logic.
  const wakeRef = useRef(() => {});

  useEffect(() => { onOpenRef.current = onOpen; }, [onOpen]);

  useEffect(() => {
    controlsRef.current = controls;
    kineticRef.current.sleeping = false;
    kineticRef.current.lowFrames = 0;
  }, [controls]);

  const resetCamera = useCallback(() => {
    const { w, h } = sizeRef.current;
    if (!w || !h) return;
    tweenRef.current = { from: { ...camRef.current }, to: fitCam(w, h), start: performance.now(), duration: 400 };
    wakeRef.current();
  }, []);

  // R-LAT-7: drop the per-frame theme-color/gradient cache the moment the
  // theme actually flips -- the next draw() rebuilds it once, every other
  // frame reuses it.
  useEffect(() => {
    const mo = new MutationObserver(() => { themeCacheRef.current = null; });
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);

  useEffect(() => {
    const wrap = wrapRef.current, canvas = canvasRef.current;
    if (!wrap || !canvas) return undefined;
    const ctx = canvas.getContext("2d");
    reducedMotionRef.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // R-LAT-7: role colors + the 4 cluster-fog gradients only depend on the
    // theme, not on anything per-frame -- rebuild once per theme flip
    // (invalidated by the MutationObserver above) instead of every draw().
    function getThemeCache(theme) {
      const cached = themeCacheRef.current;
      if (cached && cached.theme === theme) return cached;
      const dark = theme !== "light";
      const roleColors = readRoleColors(dark);
      const gradients = {};
      CLUSTER_KINDS.forEach(kind => {
        const anchor = CLUSTER_ANCHORS[kind];
        const color = roleColors[KIND_ROLE[kind]];
        const grad = ctx.createRadialGradient(anchor.x, anchor.y, 0, anchor.x, anchor.y, 180);
        grad.addColorStop(0, hexToRgba(color, 0.06 * CONTROL_DEFAULTS.fog));
        grad.addColorStop(1, hexToRgba(color, 0));
        gradients[kind] = grad;
      });
      const next = { theme, roleColors, gradients };
      themeCacheRef.current = next;
      return next;
    }

    function drawNow() {
      const { w, h } = sizeRef.current;
      if (!w || !h) return;
      const now = performance.now();
      pruneEphemerals(nodesRef.current, edgesRef.current, ephemeralIndexRef.current, now);
      ctx.setTransform(dprRef.current, 0, 0, dprRef.current, 0, 0);
      const liveGroups = groupLiveRows(liveRowsRef.current, nodesRef.current);
      const theme = document.documentElement.dataset.theme;
      const themeCache = getThemeCache(theme);
      draw(ctx, w, h, camRef.current, nodesRef.current, edgesRef.current, controlsRef.current, hoverRef.current, cometsRef.current, starsRef.current, theme, liveGroups, now, reducedMotionRef.current, themeCache);
    }
    drawNowRef.current = drawNow;

    const resize = () => {
      const rect = wrap.getBoundingClientRect();
      const w = Math.max(1, rect.width), h = Math.max(1, rect.height);
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.width = w + "px";
      canvas.style.height = h + "px";
      dprRef.current = dpr;
      sizeRef.current = { w, h };
      drawNow();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(wrap);
    resize();

    // R-LAT-7: pause the sim/draw loop entirely while the canvas is scrolled
    // out of the viewport (e.g. below the fold in RepoDetail), and resume it
    // the moment it's back -- distinct from the document.hidden check below,
    // which only covers a backgrounded tab, not an off-screen element in a
    // visible one.
    let io = null;
    if (typeof IntersectionObserver !== "undefined") {
      io = new IntersectionObserver(([entry]) => {
        const wasVisible = isVisibleRef.current;
        isVisibleRef.current = entry.isIntersecting;
        if (entry.isIntersecting && !wasVisible) resumeLoop();
      }, { threshold: 0 });
      io.observe(wrap);
    }

    function screenToWorld(clientX, clientY) {
      const rect = canvas.getBoundingClientRect();
      const cam = camRef.current;
      return { x: (clientX - rect.left - cam.x) / cam.scale, y: (clientY - rect.top - cam.y) / cam.scale };
    }

    function setHover(node) {
      hoverRef.current = node ? node.id : null;
      if (node) setHoverLabel(`${node.label} · ${node.kind} · ${((node.meta?.bytes || 0) / 1000).toFixed(1)}kb`);
      else setHoverLabel("");
    }

    let downInfo = null;
    let dragState = null;

    function onPointerDown(e) {
      const pos = screenToWorld(e.clientX, e.clientY);
      const hit = hitTestNode(nodesRef.current, pos.x, pos.y);
      downInfo = { x: e.clientX, y: e.clientY, dragged: false, hit };
      wake();
      if (hit && hit.id !== "__repo__") {
        hit.fx = hit.x; hit.fy = hit.y;
        dragState = { kind: "node", node: hit };
      } else {
        dragState = { kind: "pan", camStart: { ...camRef.current }, startX: e.clientX, startY: e.clientY };
      }
      draggingRef.current = dragState;
      canvas.setPointerCapture?.(e.pointerId);
      if (reducedMotionRef.current) drawNow();
    }

    function onPointerMove(e) {
      if (!dragState) {
        const pos = screenToWorld(e.clientX, e.clientY);
        const hit = hitTestNode(nodesRef.current, pos.x, pos.y);
        setHover(hit);
        canvas.style.cursor = hit ? (hit.kind === "agent" ? "pointer" : (hit.id === "__repo__" ? "default" : "grab")) : "default";
        if (reducedMotionRef.current) drawNow();
        return;
      }
      const dx = e.clientX - downInfo.x, dy = e.clientY - downInfo.y;
      if (Math.hypot(dx, dy) > 4) downInfo.dragged = true;
      if (dragState.kind === "node") {
        const pos = screenToWorld(e.clientX, e.clientY);
        dragState.node.fx = pos.x; dragState.node.fy = pos.y;
      } else {
        camRef.current = {
          ...camRef.current,
          x: dragState.camStart.x + (e.clientX - dragState.startX),
          y: dragState.camStart.y + (e.clientY - dragState.startY),
        };
      }
      if (reducedMotionRef.current) drawNow();
    }

    function onPointerUp() {
      if (dragState?.kind === "node" && dragState.node.id !== "__repo__") {
        if (dragState.node.kind === "leaf") {
          // Leaf robots stay pinned wherever the user drops them.
          dragState.node.fx = dragState.node.x; dragState.node.fy = dragState.node.y;
        } else {
          dragState.node.fx = null; dragState.node.fy = null;
        }
      }
      const wasClick = downInfo && !downInfo.dragged;
      const clickedHit = downInfo?.hit;
      dragState = null;
      draggingRef.current = null;
      downInfo = null;
      if (wasClick && clickedHit && clickedHit.kind === "agent") {
        onOpenRef.current?.(clickedHit.label, "agent");
      }
      if (reducedMotionRef.current) drawNow();
    }

    function onPointerLeave() {
      if (!dragState) setHover(null);
    }

    function onWheel(e) {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const sx = e.clientX - rect.left, sy = e.clientY - rect.top;
      const cam = camRef.current;
      const wx = (sx - cam.x) / cam.scale, wy = (sy - cam.y) / cam.scale;
      const factor = Math.exp(-e.deltaY * 0.001);
      const newScale = Math.min(4, Math.max(0.4, cam.scale * factor));
      camRef.current = { x: sx - wx * newScale, y: sy - wy * newScale, scale: newScale };
      if (reducedMotionRef.current) drawNow();
    }

    function onDblClick(e) {
      const pos = screenToWorld(e.clientX, e.clientY);
      const kind = hitTestClusterAnchor(pos.x, pos.y);
      if (!kind) { resetCamera(); return; }  // dbl-click empty space = reset view
      const { w, h } = sizeRef.current;
      const anchor = CLUSTER_ANCHORS[kind];
      tweenRef.current = { from: { ...camRef.current }, to: fitCamToPoint(w, h, anchor.x, anchor.y, 2.2), start: performance.now(), duration: 400 };
      wake();
    }

    function onVisibility() {
      if (!document.hidden) wake();
    }

    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointerleave", onPointerLeave);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("dblclick", onDblClick);
    document.addEventListener("visibilitychange", onVisibility);

    let rafId = null;
    let sleepDrawCounter = 0;

    // R-LAT-7: resume the rAF chain if it isn't already running (idempotent
    // -- safe to call from any handler without tracking "is it running?").
    function resumeLoop() {
      if (rafId == null && !reducedMotionRef.current && isVisibleRef.current) {
        rafId = requestAnimationFrame(step);
      }
    }
    // Interaction/new-data entry point: un-sleep the sim AND resume the loop.
    function wake() {
      kineticRef.current.sleeping = false;
      kineticRef.current.lowFrames = 0;
      resumeLoop();
    }
    wakeRef.current = wake;

    // R-LAT-7: `step` only re-arms itself at the bottom, on the single path
    // that continues looping -- NOT unconditionally at the top. Re-arming
    // eagerly at the top (the previous shape) queued the next frame before
    // this invocation had decided whether to park, so setting `rafId = null`
    // in the park branch was a no-op (a frame was already in flight) and a
    // concurrent wake() would schedule a genuine second, parallel rAF chain
    // the moment that stale frame fired -- doubling the draw rate instead of
    // parking it.
    function step() {
      if (!isVisibleRef.current) { rafId = null; return; } // IntersectionObserver resumes us
      if (document.hidden) { rafId = requestAnimationFrame(step); return; }
      const dragging = draggingRef.current;
      if (dragging || tweenRef.current) { kineticRef.current.sleeping = false; kineticRef.current.lowFrames = 0; }

      if (!kineticRef.current.sleeping) {
        const energy = simTick(nodesRef.current, edgesRef.current, controlsRef.current);
        if (energy < ENERGY_SLEEP_THRESHOLD && !dragging) {
          kineticRef.current.lowFrames++;
          if (kineticRef.current.lowFrames > SLEEP_FRAMES) kineticRef.current.sleeping = true;
        } else {
          kineticRef.current.lowFrames = 0;
        }
      }

      const tw = tweenRef.current;
      if (tw) {
        const t = Math.min(1, (performance.now() - tw.start) / tw.duration);
        const ease = 1 - Math.pow(1 - t, 3);
        camRef.current = {
          x: tw.from.x + (tw.to.x - tw.from.x) * ease,
          y: tw.from.y + (tw.to.y - tw.from.y) * ease,
          scale: tw.from.scale + (tw.to.scale - tw.from.scale) * ease,
        };
        if (t >= 1) tweenRef.current = null;
      }

      // R-LAT-7 / W1-17-nebula-engine-6: ambient embellishment (comet
      // spawning) is gated on the same sleep flag as the physics sim now --
      // previously it kept spawning forever regardless of settle state,
      // which meant `cometsRef.current` was rarely empty and the graph could
      // never reach a truly idle frame.
      const flow = controlsRef.current.cometFlow;
      if (flow > 0 && !kineticRef.current.sleeping) {
        cometTimerRef.current++;
        if (cometTimerRef.current >= 49.5 / flow) {
          cometTimerRef.current = 0;
          const visible = edgesRef.current.filter(e => controlsRef.current.crossLinks || (e.kind !== "uses" && e.kind !== "delegate"));
          trySpawnComet(cometsRef.current, visible);
        }
      }
      updateComets(cometsRef.current);

      if (kineticRef.current.sleeping) {
        // Fully settled: sim energy spent, no comets left in flight (they
        // stopped spawning above and the in-flight ones have finished), no
        // camera tween, not dragging -- draw the resting frame once, then
        // park the rAF loop entirely instead of redrawing every 3rd frame
        // forever. wake() resumes on interaction, a new live event, or a
        // repo/layer change; the IntersectionObserver resumes it on
        // scroll-back-into-view.
        if (cometsRef.current.length === 0 && !tw && !dragging) {
          drawNow();
          rafId = null;
          return;
        }
        // Still draining in-flight comets -- keep the old cheap 1-in-3 draw
        // cadence rather than a full 60fps redraw for a couple of seconds.
        sleepDrawCounter++;
        if (sleepDrawCounter % 3 !== 0) { rafId = requestAnimationFrame(step); return; }
        sleepDrawCounter = 0;
      }

      drawNow();
      rafId = requestAnimationFrame(step);
    }
    resumeLoop();

    return () => {
      ro.disconnect();
      if (io) io.disconnect();
      if (rafId) cancelAnimationFrame(rafId);
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointerleave", onPointerLeave);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("dblclick", onDblClick);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [resetCamera]);  // stable useCallback -- effect still runs once

  // Rebuild the live sim state. Intentionally keyed on [selectedRepo, layers]
  // only: AGENT_META/FILE_SIZES arrive async and feed builtNodes/builtEdges
  // above, but re-seeding the running sim/camera on every background refetch
  // would be jarring, so the next repo/layer change is what picks up fresh
  // agent/file-size data for the live sim.
  useEffect(() => {
    nodesRef.current = builtNodes.map(n => ({ ...n, vx: 0, vy: 0, x: n.fx ?? n.x, y: n.fy ?? n.y }));
    edgesRef.current = resolveEdges(nodesRef.current, builtEdges);
    cometsRef.current = [];
    ephemeralIndexRef.current = new Map();
    processedEventKeysRef.current = new Set();
    kineticRef.current = { lowFrames: 0, sleeping: false };
    const ticks = reducedMotionRef.current ? 300 : 60;
    for (let i = 0; i < ticks; i++) simTick(nodesRef.current, edgesRef.current, controlsRef.current);
    const { w, h } = sizeRef.current;
    if (w && h) camRef.current = fitCam(w, h);
    tweenRef.current = null;
    drawNowRef.current();
    wakeRef.current(); // resume the loop if a previous repo/layer had parked it
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRepo, layers]);

  // Live agent rows for the selected repo, kept in a ref so the draw loop
  // can read them every frame without a sim rebuild on every 1.5s poll.
  // R-LAT-7: App's useActiveAgents ticks every ~1-1.5s with a fresh array
  // reference even when the actual session set is unchanged (mock data's
  // secondsSinceLastEvent field keeps counting), so `repoLiveRows` gets a
  // new (often still-empty) reference on nearly every tick. Only wake the
  // parked rAF loop when the session set *content* actually changed --
  // otherwise a repo with zero live sessions would never be allowed to
  // settle, permanently defeating the park optimization above.
  const repoLiveRowsFpRef = useRef("");
  useEffect(() => {
    liveRowsRef.current = repoLiveRows;
    const fp = repoLiveRows.map(r => r.sessionId).join(",");
    const changed = fp !== repoLiveRowsFpRef.current;
    repoLiveRowsFpRef.current = fp;
    if (reducedMotionRef.current) drawNowRef.current();
    else if (changed) wakeRef.current(); // a session starting/stopping is worth a resumed frame
  }, [repoLiveRows]);

  // Real event comets + ephemeral target nodes. Dedup key is event identity
  // (see eventDedupKey), rebuilt each run so the seen-set stays bounded to
  // the ~60-event ring buffer instead of growing unbounded.
  useEffect(() => {
    if (!repo) return;
    const nodes = nodesRef.current;
    if (!nodes.length) return; // sim not built yet -- retry on the next liveEvents tick
    const repoEvents = liveEvents.filter(e => e.repo === repo.id);
    const seenKeys = new Set();
    const edges = edgesRef.current;
    const index = ephemeralIndexRef.current;
    const now = performance.now();
    const roleColors = readRoleColors();
    let sawNew = false;
    repoEvents.forEach(e => {
      const key = eventDedupKey(e);
      seenKeys.add(key);
      if (processedEventKeysRef.current.has(key)) return;
      sawNew = true;
      if (e.kind === "delegate") {
        const fromNode = resolveAgentNode(e.from, nodes);
        const toNode = nodes.find(n => n.id === "a-" + e.to)
          || getOrCreateEphemeral("delegate", e.to, fromNode, nodes, edges, index, now, roleColors);
        if (!reducedMotionRef.current) spawnLiveComet(cometsRef.current, fromNode, toNode, COMET_CAP);
      } else if (e.kind === "skill") {
        const actorNode = resolveEventActor(e.sessionId, nodes, liveRowsRef.current);
        const toNode = nodes.find(n => n.id === "s-" + e.skill)
          || getOrCreateEphemeral("skill", e.skill, actorNode, nodes, edges, index, now, roleColors);
        if (!reducedMotionRef.current) spawnLiveComet(cometsRef.current, actorNode, toNode, COMET_CAP);
      } else if (e.kind === "command") {
        const hub = nodes.find(n => n.id === "__repo__");
        const toNode = nodes.find(n => n.id === "c-" + e.cmd)
          || getOrCreateEphemeral("command", e.cmd, hub, nodes, edges, index, now, roleColors);
        if (!reducedMotionRef.current) spawnLiveComet(cometsRef.current, hub, toNode, COMET_CAP);
      } else if (e.kind === "tool") {
        const actorNode = resolveEventActor(e.sessionId, nodes, liveRowsRef.current);
        const satNode = getOrCreateEphemeral("tool", e.tool, actorNode, nodes, edges, index, now, roleColors);
        if (!reducedMotionRef.current && controlsRef.current.cometFlow > 0.8) {
          spawnLiveComet(cometsRef.current, actorNode, satNode, COMET_CAP);
        }
      }
    });
    processedEventKeysRef.current = seenKeys;
    if (sawNew) {
      wakeRef.current();
      if (reducedMotionRef.current) drawNowRef.current();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveEvents, repo?.id]);

  if (!repos.length) {
    return <div className="empty">No repos tracked yet. The nebula graph needs at least one repo to render.</div>;
  }

  const defaultCaption = `${builtNodes.length} nodes · ${builtEdges.length} links · scroll zoom · drag node · click to inspect · dbl-click to fly${repoLiveRows.length === 0 ? " · idle" : ""}`;

  return (
    <>
      {controlledLayers === undefined && (
        <div className="row gap-xs wrap mb-2" style={{ fontSize: ".66rem", color: "var(--muted)" }}>
          <span style={{ marginRight: 4, alignSelf: "center" }}>layers:</span>
          {LAYER_CHIPS.map(({ key, label, color }) => (
            <span
              key={key}
              className={"chip" + (layers[key] ? " active" : "")}
              onClick={() => setInternalLayers(l => ({ ...(l ?? fallbackLayers), [key]: !(l ?? fallbackLayers)[key] }))}
              style={{ opacity: layers[key] ? 1 : .5 }}
            >
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: `var(--${color})`, display: "inline-block", marginRight: 6 }}></span>
              {label}
            </span>
          ))}
        </div>
      )}
      <div className="nebula-caption">{hoverLabel || defaultCaption}</div>
      <div className="nebula-wrap" ref={wrapRef}>
        <canvas className="nebula-canvas" ref={canvasRef} />
      </div>
      {repoLiveRows.length > 0 && (
        <div className="mt-3">
          <LiveAgents repos={repos} agents={repoLiveRows} onOpen={onOpen} />
        </div>
      )}
    </>
  );
}
