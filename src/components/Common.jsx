import Icon from '../icons';

export const Crumbs = ({ items }) => (
  <div className="crumbs">
    <span className="crumb-prompt">›</span>
    {items.map((c, i) => (
      <span key={i}>
        {i > 0 && <span className="sep" aria-hidden="true">/</span>}
        <span className={i === items.length - 1 ? 'now' : ''}>{c}</span>
      </span>
    ))}
  </div>
);

export const Topbar = ({ crumbs, theme, setTheme, allLive, onOpenTweaks }) => (
  <div className="topbar">
    <Crumbs items={crumbs} />
    {allLive > 0 && (
      <div className="live-pill"><span className="dot"></span>{allLive} live</div>
    )}
    <div className="search-box">
      <Icon name="search" size={12} />
      <input placeholder="Search agents, skills, files…" />
      <kbd>⌘K</kbd>
    </div>
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

export const Metric = ({ label, value, unit, prefix, delta, deltaLabel, accent = 'cyan', kicker, points, sub }) => {
  // Normalise real-data points into [0,1] so the SVG geometry stays the same
  // shape regardless of metric magnitude. Falls back to the deterministic
  // pseudo-random walk when no points provided.
  const pts = (() => {
    if (!points || points.length === 0) return sparkPoints(label + String(value), 24, 0.45);
    const max = Math.max(...points, 1);
    if (max === 0) return points.map(() => 0.05);
    return points.map(v => Math.max(0.05, Math.min(0.95, v / max)));
  })();
  const W = 118, H = 38;
  const step = W / (pts.length - 1);
  const ys = pts.map(p => H - p * (H - 2) - 1);
  const linePath = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${ys[i].toFixed(1)}`).join(' ');
  const areaPath = `${linePath} L${W},${H} L0,${H} Z`;
  const lastX = (pts.length - 1) * step;
  const lastY = ys[ys.length - 1];

  let pathLen = 0;
  for (let i = 1; i < pts.length; i++) {
    const dx = step;
    const dy = ys[i] - ys[i - 1];
    pathLen += Math.sqrt(dx * dx + dy * dy);
  }
  pathLen = Math.ceil(pathLen);

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
        <svg className="metric-spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
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
          <circle className="dot-tracer" r="2.4" fill={`var(--${accent})`}>
            <animateMotion
              dur="2.6s"
              path={linePath}
              repeatCount="indefinite"
              rotate="0"
              calcMode="linear"
            />
          </circle>
          <circle className="dot-pulse" cx={lastX} cy={lastY} r="2.2" />
          <circle className="dot" cx={lastX} cy={lastY} r="2.2" />
        </svg>
      </div>
      <div className="metric-foot">
        {delta && (
          <div className={'delta' + (String(delta).startsWith('-') ? ' down' : '')}>
            {String(delta).replace(/^[+-]/, '')}
          </div>
        )}
        {deltaLabel && <div className="delta-label">{deltaLabel}</div>}
        {sub && <div className="metric-sub">{sub}</div>}
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

export const InlineSpark = ({ seed, accent = 'cyan', width = 56, height = 14, showDot = false }) => {
  const pts = sparkPoints(seed, 14, 0.55);
  const step = width / (pts.length - 1);
  const ys = pts.map(p => height - p * (height - 2) - 1);
  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${ys[i].toFixed(1)}`).join(' ');
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
