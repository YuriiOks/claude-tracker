import { useState } from 'react';
import Icon from '../icons';
import { Metric, PageHead } from './Common';
import { useDiff, useAgents, useRecentDiffs, useFileDiff } from '../api';
import { MODEL_PRICING_USD_PER_M } from '../data';
import { fmtAgo } from '../utils/time';

export const HeatmapPage = ({ repos }) => {
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const seed = (i, j) => Math.sin(i * 12.9898 + j * 78.233) * 43758.5453;
  const lvl = (i, j) => {
    const v = Math.abs(seed(i, j) % 1);
    if (j >= 9 && j <= 19 && i < 5) return v > .8 ? 4 : v > .5 ? 3 : v > .2 ? 2 : 1;
    if (j < 7 || j > 22) return v > .92 ? 1 : 0;
    return v > .85 ? 2 : v > .6 ? 1 : 0;
  };
  return (
    <>
      <PageHead title="Activity heatmap" sub="When does Claude actually run? Each cell is one hour. Darker = more sessions." />
      <div className="grid grid-cols-3 mb-4">
        <Metric label="Peak hour" value="14:00" delta="Wed · 12 sessions" accent="cyan" />
        <Metric label="Quietest day" value="Sunday" accent="purple" />
        <Metric label="Most active" value="Wed" delta="38 sessions this week" accent="gold" />
      </div>
      <div className="card-frame">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="clock" />This week · UTC+1</h2>
          <span className="frame-meta">168 cells</span>
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
                    const l = lvl(i, j);
                    return <div key={j} className="heat-cell" data-l={l || ''} title={`${d} ${String(j).padStart(2, '0')}:00 — ${l * 3} sessions`}></div>;
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
                {Array.from({ length: 48 }).map((_, j) => {
                  const v = Math.abs(Math.sin(r.id.charCodeAt(0) + j * 0.7));
                  const l = v > .8 ? 4 : v > .6 ? 3 : v > .4 ? 2 : v > .2 ? 1 : 0;
                  return <div key={j} className="heat-cell repo-cell" data-l={l || ''}></div>;
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
};

export const CostPage = ({ repos }) => {
  const { data: AGENT_META } = useAgents();
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
        <Metric label="Projected month" value={`$${(totalCost * 4.3).toFixed(0)}`} accent="purple" />
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
        </div>
      </div>

      <div className="card-frame mt-4">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="zap" />Top spenders by agent</h2>
          <span className="frame-meta">top 8</span>
        </div>
        <div className="list" style={{ border: 'none', borderRadius: 0 }}>
          <div className="list-head" style={{ gridTemplateColumns: '1.5fr 1fr 90px 90px 70px' }}>
            <span>Agent</span><span>Repo</span><span>Calls</span><span>Tokens</span><span>Cost</span>
          </div>
          {Object.entries(AGENT_META || {}).slice(0, 8).map(([name, m]) => (
            <div key={name} className="list-row clickable" style={{ gridTemplateColumns: '1.5fr 1fr 90px 90px 70px' }}>
              <span className="row gap-sm"><Icon name="bot" size={12} /><span className="tb">{name}</span></span>
              <span style={{ color: 'var(--muted)' }}>{m.repo}</span>
              <span className="tc">{m.callsToday}</span>
              <span className="tg">{((m.callsToday * m.avgTokens) / 1000).toFixed(0)}k</span>
              {/* F11: pricing from MODEL_PRICING_USD_PER_M (was hardcoded * 8) */}
              <span className="tgr">${((m.callsToday * m.avgTokens / 1e6) * MODEL_PRICING_USD_PER_M.default).toFixed(2)}</span>
            </div>
          ))}
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
  if (!D && !pickedLoading) return <div className="empty">No recent diff captured yet.</div>;

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
          <span className="frame-meta">last 72h</span>
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
        </div>
      </div>
    </>
  );
};
