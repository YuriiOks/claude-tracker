import { useState } from 'react';
import Icon from '../icons';
import { Metric, PageHead } from './Common';
import { useDiff, useCost, useRecentDiffs, useFileDiff, useHeatmap } from '../api';
import { fmtAgo } from '../utils/time';

const WEEKS_PER_MONTH = 4.33;
const TOP_AGENTS_LIMIT = 8;

export const HeatmapPage = ({ repos }) => {
  const { data: heatmapData, loading: heatmapLoading } = useHeatmap();
  const [mode, setMode] = useState('tokens');
  // The PRNG grid below is a demo fallback for `VITE_USE_MOCKS=1` only. In
  // real mode, no grid + not loading means genuinely no activity data —
  // it must never be dressed up as real stats (see `noRealData`).
  const isMockMode = import.meta.env.VITE_USE_MOCKS === '1';

  const seed = (i, j) => Math.sin(i * 12.9898 + j * 78.233) * 43758.5453;
  const lvlPrng = (i, j) => {
    const v = Math.abs(seed(i, j) % 1);
    if (j >= 9 && j <= 19 && i < 5) return v > .8 ? 4 : v > .5 ? 3 : v > .2 ? 2 : 1;
    if (j < 7 || j > 22) return v > .92 ? 1 : 0;
    return v > .85 ? 2 : v > .6 ? 1 : 0;
  };

  // Real data: heatmapData.grid[dayIndex][hour] = count, tokenGrid = token sums
  // dayLabels: ['Mon','Tue',...] with index 0 = 7 days ago
  const days = heatmapData?.dayLabels || ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const realGrid = heatmapData?.grid || null;

  // Active grid switches between session counts and token sums based on mode
  const activeGrid = (mode === 'tokens' && heatmapData?.tokenGrid) ? heatmapData.tokenGrid : realGrid;
  // Percentile-based thresholds — adapt to actual data distribution.
  // Collect sorted non-zero values; compute 25th/50th/75th breakpoints.
  const _nonZero = activeGrid ? activeGrid.flat().filter(v => v > 0).sort((a, b) => a - b) : [];
  const _pct = p => _nonZero.length ? _nonZero[Math.min(Math.floor(p * _nonZero.length), _nonZero.length - 1)] : 0;
  const [p25, p50, p75] = [_pct(0.25), _pct(0.5), _pct(0.75)];

  // No grid, not loading, not a mock build → there's simply no activity data
  // yet. Render an empty state instead of fabricated stats.
  const noRealData = !activeGrid && !heatmapLoading && !isMockMode;

  const lvlReal = (i, j) => {
    if (!activeGrid) {
      // While loading, show empty cells — avoids a PRNG flash before real
      // data arrives. Outside of mock mode, stay empty rather than fabricate.
      if (heatmapLoading || !isMockMode) return 0;
      return lvlPrng(i, j);
    }
    const v = activeGrid[i]?.[j] ?? 0;
    if (v === 0) return 0;
    // Each level covers ~25% of active hours. Highest percentile = brightest cell.
    return v >= p75 ? 4 : v >= p50 ? 3 : v >= p25 ? 2 : 1;
  };

  // Compute grid metrics from lvlReal (uses real data when available, PRNG demo in mock mode)
  const totalCells = days.length * 24;
  const grid = days.map((_, i) => Array.from({ length: 24 }, (_, j) => lvlReal(i, j)));

  // Peak hour: find (day, hour) with highest level
  let peakDay = 0, peakHour = 14, peakVal = -1;
  grid.forEach((row, i) => row.forEach((v, j) => {
    if (v > peakVal) { peakVal = v; peakDay = i; peakHour = j; }
  }));
  const peakLabel = `${String(peakHour).padStart(2, '0')}:00`;
  const peakDelta = `${days[peakDay]} · level ${peakVal}`;

  // Day totals for quietest/most-active
  const dayTotals = grid.map((row, i) => ({ day: days[i], total: row.reduce((a, v) => a + v, 0) }));
  const quietestDay = dayTotals.reduce((a, b) => b.total < a.total ? b : a).day;
  const mostActiveDay = dayTotals.reduce((a, b) => b.total > a.total ? b : a);

  // Real week total from the active grid (raw values, not levels)
  const realWeekTotal = activeGrid ? activeGrid.flat().reduce((a, v) => a + v, 0) : 0;
  const fmtWeekTotal = mode === 'tokens'
    ? realWeekTotal >= 1_000_000 ? `${(realWeekTotal / 1_000_000).toFixed(1)}M tokens`
      : realWeekTotal >= 1_000 ? `${Math.round(realWeekTotal / 1_000)}k tokens`
      : `${realWeekTotal} tokens`
    : `${realWeekTotal} session${realWeekTotal !== 1 ? 's' : ''}`;

  // Timezone
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;

  return (
    <>
      <PageHead title="Activity heatmap" sub="When does Claude actually run? Each cell is one hour. Darker = more activity." />
      {noRealData ? (
        <div className="card-frame">
          <div className="empty" style={{ padding: '2rem' }}>No activity data yet — run ingest or wait for sessions to be recorded.</div>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-3 mb-4">
            <Metric label="Peak hour" value={peakLabel} delta={peakDelta} accent="cyan" />
            <Metric label="Quietest day" value={quietestDay} accent="purple" />
            <Metric label="Most active" value={mostActiveDay.day} delta={`${fmtWeekTotal} this week`} accent="gold" />
          </div>
          <div className="card-frame">
            <div className="card-frame-head">
              <h2 className="section-title"><Icon name="clock" />This week · {tz}</h2>
              <span className="frame-meta">{totalCells} cells</span>
              <div className="seg" style={{ fontSize: '.62rem' }}>
                <button className={mode === 'sessions' ? 'active' : ''} onClick={() => setMode('sessions')}>sessions</button>
                <button className={mode === 'tokens' ? 'active' : ''} onClick={() => setMode('tokens')}>tokens</button>
              </div>
              <div className="row gap-xs" style={{ fontSize: '.6rem', color: 'var(--muted)', alignItems: 'center', gap: 6, marginLeft: 'auto' }}>
                <span style={{marginRight:4}}>Less</span>
                {[0,1,2,3,4].map(l => <span key={l} className="heat-cell legend-sw" data-l={l || ''}></span>)}
                <span style={{marginLeft:4}}>More</span>
              </div>
            </div>
            <div style={{ padding: '1rem 1.2rem' }}>
              {days.map((d, i) => (
                <div key={d} className="row gap-sm mb-2">
                  <span style={{ width: 36, fontSize: '.62rem', color: 'var(--muted)' }}>{d}</span>
                  <div style={{ flex: 1 }}>
                    <div className="heat" style={{ marginTop: 0 }}>
                      {Array.from({ length: 24 }).map((_, j) => {
                        const l = lvlReal(i, j);
                        const rawVal = activeGrid ? (activeGrid[i]?.[j] ?? 0) : 0;
                        const tipVal = mode === 'tokens'
                          ? rawVal >= 1_000_000 ? `${(rawVal / 1_000_000).toFixed(1)}M tokens`
                            : rawVal >= 1_000 ? `${(rawVal / 1_000).toFixed(0)}k tokens`
                            : `${rawVal} tokens`
                          : `${rawVal} session${rawVal !== 1 ? 's' : ''}`;
                        return <div key={j} className="heat-cell" data-l={l || ''} data-tip={`${d} ${String(j).padStart(2,'0')}:00 — ${tipVal}`}></div>;
                      })}
                    </div>
                  </div>
                </div>
              ))}
              <div className="heat-axis" style={{ paddingLeft: 44 }}>
                {Array.from({ length: 24 }).map((_, j) => <span key={j}>{j % 6 === 0 ? j : ''}</span>)}
              </div>
            </div>
          </div>
        </>
      )}

      <div className="card-frame mt-4">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="folder" />Per-repo intensity</h2>
          <span className="frame-meta">{repos.length} repos · last 48 hrs</span>
        </div>
        <div className="grid grid-cols-2" style={{ padding: '.85rem' }}>
          {repos.map(r => (
            <div key={r.id} className="cd">
              <div className="row between mb-2">
                <div className="row gap-sm">
                  <span className="sb-repo-dot" style={{ '--accent': r.accent }}></span>
                  <span className="tb">{r.name}</span>
                </div>
                <span className="bg bg-m">{r.stats.sessionsWeek} sessions</span>
              </div>
              <div className="heat" style={{ gridTemplateColumns: 'repeat(48, 1fr)', '--cell-accent': `var(--${r.accent})` }}>
                {(() => {
                  const repoSpark = mode === 'tokens'
                    ? (heatmapData?.repoTokens48h?.[r.id] ?? heatmapData?.repo48h?.[r.id])
                    : heatmapData?.repo48h?.[r.id];
                  if (!repoSpark) return Array.from({ length: 48 }).map((_, j) => (
                    <div key={j} className="heat-cell repo-cell" data-l=""></div>
                  ));
                  const rNonZero = repoSpark.filter(v => v > 0).sort((a, b) => a - b);
                  const rPct = p => rNonZero.length ? rNonZero[Math.min(Math.floor(p * rNonZero.length), rNonZero.length - 1)] : 0;
                  const [rp25, rp50, rp75] = [rPct(0.25), rPct(0.5), rPct(0.75)];
                  return Array.from({ length: 48 }).map((_, j) => {
                    const v = repoSpark[j] ?? 0;
                    const l = v === 0 ? 0 : v >= rp75 ? 4 : v >= rp50 ? 3 : v >= rp25 ? 2 : 1;
                    return <div key={j} className="heat-cell repo-cell" data-l={l || ''}></div>;
                  });
                })()}
              </div>
            </div>
          ))}
          {repos.length === 0 && <div className="empty">No repos tracked yet.</div>}
        </div>
      </div>
    </>
  );
};

export const CostPage = ({ repos, setRoute }) => {
  const { data: costData } = useCost(7);
  const byAgent = costData?.byAgent || [];
  const totalCost = repos.reduce((a, r) => a + r.stats.costWeek, 0);
  const totalTokens = repos.reduce((a, r) => a + r.stats.tokensWeek, 0);
  const max = Math.max(...repos.map(r => r.stats.costWeek), 1);
  return (
    <>
      <PageHead title="Cost & tokens" sub="Estimated spend across your tracked repositories. Calculated from token counts × model pricing." />
      <div className="grid grid-cols-4 mb-4">
        {/* F10: dropped the fake "vs last wk" / "under budget" deltas — no source.
            Avg/session is sessions-weighted across repos; Projected month = weekly × 4.3. */}
        <Metric label="Total this week" value={`$${totalCost.toFixed(2)}`} accent="green" />
        <Metric label="Tokens" value={(totalTokens / 1e6).toFixed(2)} unit="M" accent="gold" />
        <Metric
          label="Avg / session"
          value={`$${(totalCost / Math.max(1, repos.reduce((a, r) => a + r.stats.sessionsWeek, 0))).toFixed(2)}`}
          accent="cyan"
        />
        <Metric label="Projected month" value={`$${(totalCost * WEEKS_PER_MONTH).toFixed(0)}`} accent="purple" />
      </div>

      <div className="card-frame">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="dollar" />Spend by repo</h2>
          <span className="frame-meta">{repos.length} repos · this week</span>
        </div>
        <div style={{ padding: '.6rem 1rem 1rem' }}>
          {repos.map((r, i) => (
            <div key={r.id} style={{ padding: '.6rem 0', borderBottom: i === repos.length - 1 ? 'none' : '1px solid var(--brd2)' }}>
              <div className="row between mb-2">
                <div className="row gap-sm">
                  <span className="sb-repo-dot" style={{ '--accent': r.accent }}></span>
                  <span className="tb" style={{ fontWeight: 600 }}>{r.name}</span>
                  <span className="mono" style={{ fontSize: '.62rem', color: 'var(--muted)' }}>{r.branch}</span>
                </div>
                <div className="row gap-md">
                  <span className="tg" style={{ fontWeight: 600 }}>${r.stats.costWeek.toFixed(2)}</span>
                  <span style={{ fontSize: '.66rem', color: 'var(--muted)' }}>{(r.stats.tokensWeek / 1e6).toFixed(2)}M tokens</span>
                </div>
              </div>
              <div style={{ height: 6, borderRadius: 3, background: 'var(--brd2)', overflow: 'hidden' }}>
                <div style={{
                  height: '100%',
                  width: `${(r.stats.costWeek / max) * 100}%`,
                  background: `linear-gradient(90deg, ${r.accent}, transparent)`,
                  transition: 'width .6s var(--ease)'
                }}></div>
              </div>
            </div>
          ))}
          {repos.length === 0 && <div className="empty">No repos tracked yet.</div>}
        </div>
      </div>

      <div className="card-frame mt-4">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="zap" />Top spenders by agent</h2>
          <span className="frame-meta">top {TOP_AGENTS_LIMIT} · 7 days</span>
        </div>
        <div className="list" style={{ border: 'none', borderRadius: 0 }}>
          <div className="list-head" style={{ gridTemplateColumns: '2fr 90px 110px 70px' }}>
            <span>Agent</span><span>Calls</span><span>Tokens</span><span>Cost</span>
          </div>
          {byAgent.slice(0, TOP_AGENTS_LIMIT).map(a => (
            <div key={a.agent} className={"list-row" + (setRoute ? " clickable" : "")} style={{ gridTemplateColumns: '2fr 90px 110px 70px' }} onClick={setRoute ? () => setRoute({ page: 'agent', name: a.agent, kind: 'agent', repoId: null }) : undefined}>
              <span className="row gap-sm"><Icon name="bot" size={12} /><span className="tb">{a.agent}</span></span>
              <span className="tc">{a.calls}</span>
              <span className="tg">{a.tokens >= 1_000_000 ? (a.tokens / 1_000_000).toFixed(1) + 'M' : (a.tokens / 1000).toFixed(0) + 'k'}</span>
              <span className="tgr">${a.cost.toFixed(2)}</span>
            </div>
          ))}
          {byAgent.length === 0 && <div className="empty">No agent data yet — run ingest first.</div>}
        </div>
      </div>
    </>
  );
};

export const DiffPage = () => {
  // `selected` overrides the default headline diff when the user clicks a
  // row in the recent-diffs list. Cleared when the user clicks the same
  // row again or hits "Show latest".
  const [selected, setSelected] = useState(null);  // { repo, path } | null
  const { data: defaultDiff } = useDiff();
  const { data: recentDiffs } = useRecentDiffs();
  const { data: pickedDiff, loading: pickedLoading } = useFileDiff(
    selected?.repo, selected?.path,
  );

  // The headline shows whichever diff is "active": the user pick if any,
  // otherwise the most-recent diff from /api/diffs/recent.
  const D = selected ? pickedDiff : defaultDiff;
  // A 404 here (e.g. the file is already committed, no diff to show) must
  // only blank the detail pane — the page shell and recent-diffs list below
  // stay mounted so the user can still navigate.
  const noDiff = !D && !pickedLoading;

  const adds = (D?.hunks || []).reduce((a, h) => a + h.lines.filter(l => l.type === 'add').length, 0);
  const dels = (D?.hunks || []).reduce((a, h) => a + h.lines.filter(l => l.type === 'del').length, 0);

  return (
    <>
      <PageHead title="Recent diffs" sub="When Claude edits files, the diff is captured here. Click a row below to inspect that file's current changes." />
      {D && (
        <div className="row gap-sm mb-3">
          <span className="bg bg-c"><Icon name="bot" size={10} />{D.agent || '—'}</span>
          {D.session && <span className="bg bg-m">session {D.session}</span>}
          <span className="bg bg-gr">+{adds}</span>
          <span className="bg bg-ro">−{dels}</span>
          {selected && (
            <button
              className="link-btn"
              style={{ marginLeft: 'auto' }}
              onClick={() => setSelected(null)}
              title="Return to the most recent diff"
            >Show latest →</button>
          )}
        </div>
      )}
      {pickedLoading && !pickedDiff && (
        <div className="empty" style={{ minHeight: 60 }}>Loading diff…</div>
      )}
      {noDiff && (
        <div className="row gap-sm mb-3" style={{ alignItems: 'center' }}>
          <div className="empty" style={{ minHeight: 60, flex: 1 }}>
            {selected ? "No diff for this file — it's already committed, nothing pending." : 'No recent diff captured yet.'}
          </div>
          {selected && (
            <button className="link-btn" onClick={() => setSelected(null)} title="Return to the most recent diff">
              Show latest →
            </button>
          )}
        </div>
      )}
      {D && (
        <div className="diff">
          <div className="diff-header">
            <Icon name="file" size={12} />
            <span className="mono">{D.file}</span>
          </div>
          {D.hunks.map((h, i) => (
            <div key={i} className="diff-hunk">
              <div className="diff-hunk-header mono">{h.header}</div>
              {h.lines.map((l, j) => (
                <span key={j} className={'diff-line ' + l.type}>
                  {l.type === 'add' ? '+' : l.type === 'del' ? '−' : ' '}
                  {l.text}
                </span>
              ))}
            </div>
          ))}
        </div>
      )}

      <div className="card-frame mt-4">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="diff" />Recent diffs across repos</h2>
          <span className="frame-meta">{recentDiffs?.length ?? 0} files</span>
        </div>
        <div className="list" style={{ border: 'none', borderRadius: 0 }}>
          <div className="list-head" style={{ gridTemplateColumns: '90px 1fr 110px 90px 90px' }}>
            <span>Time</span><span>File</span><span>Repo</span><span>Lines</span><span>Agent</span>
          </div>
          {(recentDiffs || []).map((d) => {
            const isSelected = selected && selected.repo === d.repo && selected.path === d.file;
            return (
              <div
                key={`${d.repo}/${d.file}`}
                className={'list-row clickable' + (isSelected ? ' active' : '')}
                style={{ gridTemplateColumns: '90px 1fr 110px 90px 90px' }}
                onClick={() => setSelected(isSelected ? null : { repo: d.repo, path: d.file })}
                title={isSelected ? 'Click to clear selection' : `View diff for ${d.file}`}
              >
                <span className="mono" style={{ fontSize: '.66rem', color: 'var(--muted)' }}>{fmtAgo(d.ts)}</span>
                <span className="mono" style={{ fontSize: '.7rem' }}>{d.file}</span>
                <span style={{ color: 'var(--muted)' }}>{d.repo}</span>
                <span className="mono"><span className="tgr">+{d.adds}</span> <span className="tro">−{d.dels}</span></span>
                <span className="tp">{d.agent || '—'}</span>
              </div>
            );
          })}
          {(recentDiffs || []).length === 0 && <div className="empty">No diffs captured yet.</div>}
        </div>
      </div>
    </>
  );
};
