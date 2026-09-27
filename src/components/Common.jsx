import { useState } from 'react';
import Icon from '../icons';
import { useBackendStatus, useRetrying, retryFetches } from '../api';
import CommandPalette from './CommandPalette';

// Crumb items are { label, route } — `route` is a route object passed
// straight to setRoute(), or null/undefined for the current (non-clickable)
// segment, which is always the last one.
export const Crumbs = ({ items, setRoute }) => (
  <nav className="crumbs" aria-label="Breadcrumb">
    <span className="crumb-prompt">›</span>
    {items.map((c, i) => {
      const clickable = !!c.route && setRoute && i !== items.length - 1;
      return (
        <span key={i}>
          {i > 0 && <span className="sep" aria-hidden="true">/</span>}
          {clickable ? (
            <button type="button" className="crumb-link" onClick={() => setRoute(c.route)}>
              {c.label}
            </button>
          ) : (
            <span className={i === items.length - 1 ? 'now' : ''}>{c.label}</span>
          )}
        </span>
      );
    })}
  </nav>
);

// R-UX-2: honest data-state pill. Renders nothing when everything's fine
// (online, or mock mode is its own explicit pill anyway). aria-live so
// screen readers hear a state transition, not just sighted users.
export const BackendStatusPill = () => {
  const { state } = useBackendStatus();
  const retrying = useRetrying();
  if (state === 'online') return null;
  const cfg = {
    mock: { label: 'MOCK DATA', cls: 'bs-mock' },
    stale: { label: 'cached · ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), cls: 'bs-stale' },
    offline: { label: 'Backend unreachable — showing sample/cached data', cls: 'bs-offline' },
    // R-SEC-1: the backend is reachable but wants a pairing token. In LAN
    // mode (see backend/app/security.py) this is the *only* way to see this
    // pill — Host-based trust is off entirely there, so the Tweaks panel's
    // "Pair a phone" section (which needs that same trust to fetch a token)
    // 403s and quietly hides itself. Point at `make pair` / `make
    // docker-pair` first; clicking still opens Tweaks for the rare
    // non-LAN-mode case where that section works.
    auth: { label: 'Pair this device', hint: 'Run `make pair` (or `make docker-pair`) on the Mac running claude-tracker — or open Tweaks → Pair a phone there', cls: 'bs-auth' },
  }[state];
  if (!cfg) return null;
  const openTweaks = () => window.postMessage({ type: '__activate_edit_mode' }, window.location.origin);
  return (
    <div
      className={'backend-status ' + cfg.cls}
      role="status"
      aria-live="polite"
      title={cfg.hint}
      onClick={state === 'auth' ? openTweaks : undefined}
      style={state === 'auth' ? { cursor: 'pointer' } : undefined}
    >
      <span className="dot"></span>
      {/* Full label on desktop; visually collapses to just the dot + retry
          on narrow viewports (see .backend-status media query) but stays in
          the accessibility tree via sr-only so screen readers always hear it. */}
      <span className="backend-status-label">{cfg.label}</span>
      {state === 'offline' && (
        <button type="button" className="backend-status-retry" onClick={() => retryFetches()} disabled={retrying}>
          {retrying ? 'Retrying…' : 'Retry'}
        </button>
      )}
    </div>
  );
};

export const Topbar = ({ crumbs, setRoute, theme, setTheme, allLive, onOpenTweaks, repos }) => (
  <div className="topbar">
    <Crumbs items={crumbs} setRoute={setRoute} />
    <BackendStatusPill />
    {allLive > 0 && (
      <div className="live-pill"><span className="dot"></span>{allLive} live</div>
    )}
    <CommandPalette repos={repos} setRoute={setRoute} />
    <button className="icon-btn" title={theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
      <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
    </button>
    <button className="icon-btn" title="Open Tweaks" onClick={onOpenTweaks}><Icon name="settings" /></button>
  </div>
);

function sparkPoints(seed, n = 14, vol = 0.6) {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  const pts = [];
  let v = 0.5;
  for (let i = 0; i < n; i++) {
    h = (h * 1664525 + 1013904223) >>> 0;
    const r = ((h >>> 8) & 0xffff) / 0xffff;
    v += (r - 0.5) * vol;
    v = Math.max(0.05, Math.min(0.95, v));
    pts.push(v);
  }
  pts[n - 1] = Math.min(0.95, pts[n - 1] + 0.1);
  return pts;
}

export { sparkPoints };

export const Metric = ({ label, value, unit, prefix, delta, deltaLabel, accent = 'cyan', kicker, points, sub, caption }) => {
  // Real points render as-is (normalised into [0,1] for consistent SVG
  // geometry); missing/empty points render an honest "no data" placeholder
  // instead of a fabricated pseudo-random walk.
  const hasPoints = !!(points && points.length > 0);
  const pts = hasPoints
    ? (() => {
        const max = Math.max(...points, 1);
        if (max === 0) return points.map(() => 0.05);
        return points.map(v => Math.max(0.05, Math.min(0.95, v / max)));
      })()
    : [];
  const W = 118, H = 38;
  // A single-point series has no interval to divide by — duplicate it so
  // the geometry degenerates into a flat line instead of Infinity/NaN.
  const gpts = hasPoints ? (pts.length > 1 ? pts : [pts[0] ?? 0.5, pts[0] ?? 0.5]) : [];
  const step = hasPoints ? W / (gpts.length - 1) : 0;
  const ys = hasPoints ? gpts.map(p => H - p * (H - 2) - 1) : [];
  const linePath = hasPoints
    ? gpts.map((p, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${ys[i].toFixed(1)}`).join(' ')
    : '';
  const areaPath = hasPoints ? `${linePath} L${W},${H} L0,${H} Z` : '';
  const lastX = hasPoints ? (gpts.length - 1) * step : 0;
  const lastY = hasPoints ? ys[ys.length - 1] : 0;

  let pathLen = 0;
  if (hasPoints) {
    for (let i = 1; i < gpts.length; i++) {
      const dx = step;
      const dy = ys[i] - ys[i - 1];
      pathLen += Math.sqrt(dx * dx + dy * dy);
    }
    pathLen = Math.ceil(pathLen);
  }
  // Tracer dot only makes sense when the series actually moves — a flat
  // real series (e.g. all-zero) shouldn't animate a dot along a flat line.
  const hasVariance = hasPoints && Math.max(...points) !== Math.min(...points);

  const [hoverIdx, setHoverIdx] = useState(null);
  const handleSparkMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const i = Math.round((e.clientX - rect.left) / rect.width * (points.length - 1));
    setHoverIdx(Math.max(0, Math.min(points.length - 1, i)));
  };

  const display = value;

  return (
    <div className="metric" style={{ '--accent': `var(--${accent})` }}>
      <div className="metric-top">
        <div className="ml">{label}</div>
        {kicker && <div className="metric-kicker">{kicker}</div>}
      </div>
      <div className="metric-row">
        <div className="mv">
          {prefix && <span className="prefix">{prefix}</span>}
          {display}{unit && <span className="unit">{unit}</span>}
        </div>
        <span style={{ position: 'relative' }}>
          <svg
            className="metric-spark"
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            aria-hidden="true"
            onMouseMove={hasPoints ? handleSparkMove : undefined}
            onMouseLeave={hasPoints ? () => setHoverIdx(null) : undefined}
          >
            {hasPoints ? (
              <>
                <defs>
                  <linearGradient id={`sparkFill-${accent}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={`var(--${accent})`} stopOpacity="0.35" />
                    <stop offset="100%" stopColor={`var(--${accent})`} stopOpacity="0" />
                  </linearGradient>
                </defs>
                <path className="area" d={areaPath} style={{ fill: `url(#sparkFill-${accent})` }} />
                <path className="line" d={linePath} style={{ strokeDasharray: pathLen, strokeDashoffset: pathLen, '--pathLen': pathLen }} />
                {/* Tracer dot — rides the full path start→end, repeats forever.
                    Synced with sparkDraw on first paint, then loops indefinitely. */}
                {hasVariance && (
                  <circle className="dot-tracer" r="2.4" fill={`var(--${accent})`}>
                    <animateMotion
                      dur="2.6s"
                      path={linePath}
                      repeatCount="indefinite"
                      rotate="0"
                      calcMode="linear"
                    />
                  </circle>
                )}
                <circle className="dot-pulse" cx={lastX} cy={lastY} r="2.2" />
                <circle className="dot" cx={lastX} cy={lastY} r="2.2" />
              </>
            ) : (
              <>
                <title>no history data</title>
                <path d="M0,30 L118,30" className="line" strokeDasharray="3 4" opacity="0.35" fill="none" />
              </>
            )}
          </svg>
          {hasPoints && hoverIdx != null && (
            <div style={{ position: 'absolute', bottom: '100%', right: 0, background: 'var(--card)', border: '1px solid var(--brd)', borderRadius: 4, padding: '2px 6px', fontSize: 10, fontFamily: 'Fira Code, monospace', whiteSpace: 'nowrap', pointerEvents: 'none' }}>
              {points[hoverIdx]} · -{points.length - 1 - hoverIdx}h
            </div>
          )}
        </span>
      </div>
      <div className="metric-foot">
        {delta && (
          <div className={'delta' + (String(delta).startsWith('-') ? ' down' : '')}>
            {String(delta).replace(/^[+-]/, '')}
          </div>
        )}
        {deltaLabel && <div className="delta-label">{deltaLabel}</div>}
        {sub && <div className="metric-sub">{sub}</div>}
        {caption && <div className="delta-label" style={{ marginTop: 2 }}>{caption}</div>}
      </div>
    </div>
  );
};

export const Status = ({ kind, size = 'md' }) => {
  const labels = { running: 'Running', completed: 'Completed', idle: 'Idle', failed: 'Failed', queued: 'Queued' };
  return (
    <span className={'status status-' + kind + (size === 'sm' ? ' status-sm' : '')}>
      <span className="dot"></span>{labels[kind] || kind}
    </span>
  );
};

export const Tag = ({ children, accent = 'cyan' }) => (
  <span className="ctag" style={{ '--accent': `var(--${accent})` }}>{children}</span>
);

export const InlineSpark = ({ seed, accent = 'cyan', width = 56, height = 14, showDot = false, points }) => {
  const rawPts = (points && points.length > 0) ? points : sparkPoints(seed, 14, 0.55);
  const maxVal = Math.max(...rawPts, 1);
  const pts = rawPts.map(v => Math.max(0.05, Math.min(0.95, v / maxVal)));
  // Guard the single-point case the same way Metric's sparkline does.
  const spts = pts.length > 1 ? pts : [pts[0] ?? 0.5, pts[0] ?? 0.5];
  const step = width / (spts.length - 1);
  const ys = spts.map(p => height - p * (height - 2) - 1);
  const path = spts.map((p, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${ys[i].toFixed(1)}`).join(' ');
  const areaPath = `${path} L${width.toFixed(1)},${height} L0,${height} Z`;
  const gradId = `inlSpark-${seed}-${accent}`;
  const lastX = (width).toFixed(1);
  const lastY = ys[ys.length - 1].toFixed(2);
  return (
    <svg className="inline-spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={`var(--${accent})`} stopOpacity="0.32" />
          <stop offset="100%" stopColor={`var(--${accent})`} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradId})`} stroke="none" />
      <path d={path} fill="none" stroke={`var(--${accent})`} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" opacity="0.95" />
      {showDot && (
        <>
          <circle className="inl-dot-pulse" cx={lastX} cy={lastY} r="2" fill="none" stroke={`var(--${accent})`} strokeWidth="1" opacity="0.7" />
          <circle cx={lastX} cy={lastY} r="1.6" fill={`var(--${accent})`} />
        </>
      )}
    </svg>
  );
};

export const Tabs = ({ items, value, onChange }) => (
  <div className="tabs">
    {items.map(t => (
      <button key={t.id} className={'tab' + (t.id === value ? ' active' : '')}
        onClick={() => onChange(t.id)}>
        {t.icon && <Icon name={t.icon} size={12} />}
        {t.label}
        {t.count != null && <span className="ct">{t.count}</span>}
      </button>
    ))}
  </div>
);

export const ViewToggle = ({ value, onChange, options }) => {
  const idx = Math.max(0, options.findIndex(o => o.id === value));
  const n = options.length;
  return (
    <div className="view-toggle" role="radiogroup" data-count={n}>
      <span
        className="view-toggle-thumb"
        style={{ left: `calc(3px + ${idx} * ((100% - 6px) / ${n}))`, width: `calc((100% - 6px) / ${n})` }}
        aria-hidden="true"
      />
      {options.map(o => {
        const active = value === o.id;
        return (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={active}
            className={active ? 'active' : ''}
            onClick={() => onChange(o.id)}
          >
            <Icon name={o.icon} size={13} />
            <span>{o.label}</span>
          </button>
        );
      })}
    </div>
  );
};

export const PageHead = ({ title, sub, eyebrow, actions, accent, stats }) => (
  <div className="page-head">
    <div className="page-head-text">
      {eyebrow && <div className="page-eyebrow">{eyebrow}</div>}
      <h1 className="page-title" style={accent ? { color: accent } : {}}>
        {title}
      </h1>
      {sub && <div className="page-sub">{sub}</div>}
      {stats && <div className="page-stats">{stats}</div>}
    </div>
    {actions && <div className="page-actions">{actions}</div>}
  </div>
);
