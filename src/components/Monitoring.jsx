import { useState, useEffect } from 'react';
import Icon from '../icons';
import { PageHead } from './Common';
import {
  useTelemetryConfig,
  setTelemetry,
  getTelemetry,
  useOtelSummary,
  useOtelMetrics,
} from '../api';
import { fmtAgo } from '../utils/time';

// ── helpers ──────────────────────────────────────────────────────────────────

function fmtDate(isoTs) {
  if (!isoTs) return '—';
  const d = new Date(isoTs);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
}

function fmtActiveSec(sec) {
  const s = Math.round(sec ?? 0);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r === 0 ? `${m}m` : `${m}m ${r}s`;
}

// ── sub-components ───────────────────────────────────────────────────────────

function Toggle({ checked, onChange, disabled }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      className={'mon-toggle' + (checked ? ' on' : '') + (disabled ? ' disabled' : '')}
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
    >
      <span className="mon-toggle-thumb" />
    </button>
  );
}

function StatusBadge({ ok }) {
  return (
    <span className={'mon-badge' + (ok ? ' ok' : ' off')}>
      {ok ? 'Enabled' : 'Disabled'}
    </span>
  );
}

// ── main panels ──────────────────────────────────────────────────────────────

function TelemetryCard({ config, onConfigChange }) {
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState(null);

  const logToolDetails = config.options?.logToolDetails ?? false;
  const logUserPrompts = config.options?.logUserPrompts ?? false;

  async function applyChange(patch) {
    if (busy) return;
    setBusy(true);
    setSaveError(null);
    const payload = {
      enabled: patch.enabled ?? config.enabled,
      logToolDetails: patch.logToolDetails ?? logToolDetails,
      logUserPrompts: patch.logUserPrompts ?? logUserPrompts,
      ifUnchangedSince: config.mtime,
    };
    try {
      const updated = await setTelemetry(payload);
      onConfigChange(updated);
    } catch (err) {
      if (err.stale) {
        try {
          const fresh = await getTelemetry();
          onConfigChange(fresh);
          setSaveError('Settings changed on disk — refreshed. Please retry.');
        } catch {
          setSaveError('Could not reload settings. Try again.');
        }
      } else {
        setSaveError(err.message || 'Save failed.');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card-frame mon-control-card">
      <div className="card-frame-head">
        <h2 className="section-title">
          <Icon name="zap" />
          Telemetry control
        </h2>
        <StatusBadge ok={config.enabled} />
      </div>
      <div className="mon-card-body">
        <div className="mon-row">
          <div className="mon-row-label">
            <span className="mon-label-main">Enable telemetry</span>
            <span className="mon-label-sub">Send OTel logs + metrics to the local endpoint</span>
          </div>
          <Toggle checked={config.enabled} onChange={v => applyChange({ enabled: v })} disabled={busy} />
        </div>

        <div className={'mon-row mon-sub-row' + (!config.enabled ? ' muted' : '')}>
          <div className="mon-row-label">
            <span className="mon-label-main">Log tool details</span>
            <span className="mon-label-sub">Include tool input/output in events</span>
          </div>
          <Toggle checked={logToolDetails} onChange={v => applyChange({ logToolDetails: v })} disabled={busy || !config.enabled} />
        </div>

        <div className={'mon-row mon-sub-row' + (!config.enabled ? ' muted' : '')}>
          <div className="mon-row-label">
            <span className="mon-label-main">Log user prompts</span>
            <span className="mon-label-sub">Include prompt text in events (privacy-sensitive)</span>
          </div>
          <Toggle checked={logUserPrompts} onChange={v => applyChange({ logUserPrompts: v })} disabled={busy || !config.enabled} />
        </div>

        {saveError && (
          <p className="mon-save-error">{saveError}</p>
        )}

        <div className="mon-meta-grid">
          <span className="mon-meta-label">Settings file</span>
          <code className="mon-meta-val">{config.settingsPath || '—'}</code>
          <span className="mon-meta-label">Logs URL</span>
          <code className="mon-meta-val">{config.ingestUrl || '—'}</code>
          <span className="mon-meta-label">Metrics URL</span>
          <code className="mon-meta-val">{config.metricsUrl || '—'}</code>
          <span className="mon-meta-label">Total events</span>
          <span className="mon-meta-val">{config.eventTotal?.toLocaleString() ?? '0'}</span>
          <span className="mon-meta-label">Last event</span>
          <span className="mon-meta-val">{fmtDate(config.lastEventAt)}</span>
          <span className="mon-meta-label">Total metrics</span>
          <span className="mon-meta-val">{config.metricTotal?.toLocaleString() ?? '0'}</span>
          <span className="mon-meta-label">Last metric</span>
          <span className="mon-meta-val">{fmtDate(config.lastMetricAt)}</span>
        </div>

        <p className="mon-notice">
          Changes take effect on the next <code>claude</code> launch, not running sessions.
        </p>
      </div>
    </div>
  );
}

function ErrorsFeed({ errors }) {
  if (!errors || errors.length === 0) {
    return (
      <div className="card-frame">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="shield" />API errors</h2>
        </div>
        <p className="mon-empty">No API errors in the last 24h ✓</p>
      </div>
    );
  }

  return (
    <div className="card-frame">
      <div className="card-frame-head">
        <h2 className="section-title"><Icon name="shield" />API errors</h2>
        <span className="frame-meta">{errors.length} in 24h</span>
      </div>
      <div className="mon-errors">
        {errors.map((e, i) => (
          <div key={i} className="mon-error-row">
            <div className="mon-error-left">
              <span className="mon-err-name">{e.eventName}</span>
              {e.model && <span className="mon-err-model">{e.model}</span>}
              <span className="mon-err-msg">{e.error}</span>
            </div>
            <div className="mon-error-right">
              {e.statusCode && <span className="mon-status-code">{e.statusCode}</span>}
              {e.attempt > 1 && <span className="mon-attempt">attempt {e.attempt}</span>}
              <span className="mon-ts" title={e.ts}>{fmtAgo(e.ts)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function LatencyTable({ toolLatency }) {
  if (!toolLatency || toolLatency.length === 0) {
    return (
      <div className="card-frame">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="activity" />Tool latency</h2>
        </div>
        <p className="mon-empty">No latency data in this window.</p>
      </div>
    );
  }

  const sorted = [...toolLatency].sort((a, b) => b.p95Ms - a.p95Ms);

  return (
    <div className="card-frame">
      <div className="card-frame-head">
        <h2 className="section-title"><Icon name="activity" />Tool latency</h2>
        <span className="frame-meta">sorted by p95</span>
      </div>
      <div className="mon-table-wrap">
        <table className="mon-table">
          <thead>
            <tr>
              <th>Tool</th>
              <th className="num">Count</th>
              <th className="num">p50 ms</th>
              <th className="num">p95 ms</th>
              <th className="num">max ms</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(row => (
              <tr key={row.tool}>
                <td className="mon-tool-name">{row.tool}</td>
                <td className="num">{row.count}</td>
                <td className="num">{row.p50Ms}</td>
                <td className="num mon-p95">{row.p95Ms}</td>
                <td className="num muted">{row.maxMs}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EventOverview({ counts, eventTotal }) {
  const entries = Object.entries(counts || {});

  return (
    <div className="card-frame">
      <div className="card-frame-head">
        <h2 className="section-title"><Icon name="cpu" />Event overview</h2>
        <span className="frame-meta">{eventTotal?.toLocaleString() ?? 0} total · 24h</span>
      </div>
      {entries.length === 0 ? (
        <p className="mon-empty">No events in this window.</p>
      ) : (
        <div className="mon-counts-grid">
          {entries.map(([name, count]) => (
            <div key={name} className="mon-count-cell">
              <span className="mon-count-val">{count.toLocaleString()}</span>
              <span className="mon-count-name">{name.replace(/_/g, ' ')}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Colours rotated across bar items — only design tokens, both-theme safe.
const BAR_TOKENS = ['--cyan', '--purple', '--teal', '--orange', '--green', '--rose'];

function BarRow({ label, value, maxValue, colorToken }) {
  const pct = maxValue > 0 ? Math.round((value / maxValue) * 100) : 0;
  return (
    <div className="mon-bar-row">
      <span className="mon-bar-label">{label}</span>
      <div className="mon-bar-track">
        <div
          className="mon-bar-fill"
          style={{ width: `${pct}%`, background: `var(${colorToken})` }}
        />
      </div>
      <span className="mon-bar-val">{value}</span>
    </div>
  );
}

function CostPanel({ metrics }) {
  const cost = metrics?.cost;
  if (!cost) {
    return (
      <div className="card-frame">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="cpu" />Cost</h2>
        </div>
        <p className="mon-empty">No cost metrics in this window.</p>
      </div>
    );
  }
  const totalFmt = `$${(cost.total ?? 0).toFixed(2)}`;
  const maxModel = Math.max(...(cost.byModel?.map(r => r.cost) ?? [0]));
  const maxSource = Math.max(...(cost.bySource?.map(r => r.cost) ?? [0]));
  return (
    <div className="card-frame">
      <div className="card-frame-head">
        <h2 className="section-title"><Icon name="cpu" />Cost</h2>
        <span className="frame-meta">{totalFmt} · 24h</span>
      </div>
      <div className="mon-metrics-body">
        {cost.byModel && cost.byModel.length > 0 && (
          <div className="mon-metrics-section">
            <p className="mon-metrics-section-label">By model</p>
            {cost.byModel.map((row, i) => (
              <BarRow
                key={row.model}
                label={row.model}
                value={`$${row.cost.toFixed(2)}`}
                maxValue={maxModel}
                colorToken={BAR_TOKENS[i % BAR_TOKENS.length]}
              />
            ))}
          </div>
        )}
        {cost.bySource && cost.bySource.length > 0 && (
          <div className="mon-metrics-section">
            <p className="mon-metrics-section-label">By source</p>
            {cost.bySource.map((row, i) => (
              <BarRow
                key={row.querySource}
                label={row.querySource}
                value={`$${row.cost.toFixed(2)}`}
                maxValue={maxSource}
                colorToken={BAR_TOKENS[i % BAR_TOKENS.length]}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TokenPanel({ metrics }) {
  const tokens = metrics?.tokens;
  if (!tokens) {
    return (
      <div className="card-frame">
        <div className="card-frame-head">
          <h2 className="section-title"><Icon name="activity" />Tokens</h2>
        </div>
        <p className="mon-empty">No token metrics in this window.</p>
      </div>
    );
  }
  const totalFmt = (tokens.total ?? 0).toLocaleString();
  const maxType = Math.max(...(tokens.byType?.map(r => r.tokens) ?? [0]));
  return (
    <div className="card-frame">
      <div className="card-frame-head">
        <h2 className="section-title"><Icon name="activity" />Tokens</h2>
        <span className="frame-meta">{totalFmt} · 24h</span>
      </div>
      <div className="mon-metrics-body">
        {tokens.byType && tokens.byType.length > 0 && (
          <div className="mon-metrics-section">
            <p className="mon-metrics-section-label">By type</p>
            {tokens.byType.map((row, i) => (
              <BarRow
                key={row.type}
                label={row.type}
                value={row.tokens.toLocaleString()}
                maxValue={maxType}
                colorToken={BAR_TOKENS[i % BAR_TOKENS.length]}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SessionStatsPanel({ metrics }) {
  const sessions = metrics?.sessions ?? 0;
  const activeTimeSec = metrics?.activeTimeSec ?? 0;
  return (
    <div className="card-frame">
      <div className="card-frame-head">
        <h2 className="section-title"><Icon name="zap" />Session stats</h2>
        <span className="frame-meta">24h</span>
      </div>
      <div className="mon-counts-grid">
        <div className="mon-count-cell">
          <span className="mon-count-val">{sessions}</span>
          <span className="mon-count-name">sessions</span>
        </div>
        <div className="mon-count-cell">
          <span className="mon-count-val">{fmtActiveSec(activeTimeSec)}</span>
          <span className="mon-count-name">active time</span>
        </div>
      </div>
    </div>
  );
}

function EmptyCTA({ onEnable, busy }) {
  return (
    <div className="mon-cta">
      <div className="mon-cta-icon"><Icon name="zap" /></div>
      <h2 className="mon-cta-title">Telemetry is off</h2>
      <p className="mon-cta-sub">Enable it to populate this view with event counts, latency, and error data from your Claude sessions.</p>
      <button className="mon-cta-btn" onClick={onEnable} disabled={busy}>
        {busy ? 'Enabling…' : 'Enable telemetry'}
      </button>
      <p className="mon-cta-note">Changes take effect on the next <code>claude</code> launch, not running sessions.</p>
    </div>
  );
}

// ── page ─────────────────────────────────────────────────────────────────────

export default function MonitoringPage() {
  const { data: remoteConfig, loading: configLoading } = useTelemetryConfig();
  const [config, setConfig] = useState(null);
  const { data: summary } = useOtelSummary(10000);
  const { data: metrics } = useOtelMetrics(10000);

  // Sync local config state when remote data arrives (initial fetch or change)
  useEffect(() => {
    if (remoteConfig) setConfig(remoteConfig);
  }, [remoteConfig]);

  const [ctaBusy, setCtaBusy] = useState(false);

  if (configLoading && !config) {
    return <div className="empty" style={{ padding: '2rem', color: 'var(--muted)' }}>Loading…</div>;
  }

  if (!config) return null;

  // Global CTA: telemetry off + no summary events in this window
  const showCTA = !config.enabled && (summary?.eventTotal ?? 0) === 0;

  async function handleCtaEnable() {
    setCtaBusy(true);
    try {
      const updated = await setTelemetry({
        enabled: true,
        logToolDetails: config.options?.logToolDetails ?? false,
        logUserPrompts: config.options?.logUserPrompts ?? false,
        ifUnchangedSince: config.mtime,
      });
      setConfig(updated);
    } catch (err) {
      if (err.stale) {
        try { setConfig(await getTelemetry()); } catch { /* ignore */ }
      }
    } finally {
      setCtaBusy(false);
    }
  }

  return (
    <>
      <PageHead
        title="Monitoring"
        sub="OTel telemetry status, cost, tokens, event counts, tool latency, and API errors from Claude sessions."
      />

      <TelemetryCard config={config} onConfigChange={setConfig} />

      {showCTA ? (
        <EmptyCTA onEnable={handleCtaEnable} busy={ctaBusy} />
      ) : (
        <>
          <div className="mon-panels mon-metrics-panels">
            <CostPanel metrics={metrics} />
            <TokenPanel metrics={metrics} />
            <SessionStatsPanel metrics={metrics} />
          </div>
          <div className="mon-panels">
            <EventOverview counts={summary?.counts} eventTotal={summary?.eventTotal} />
            <ErrorsFeed errors={summary?.errors} />
            <LatencyTable toolLatency={summary?.toolLatency} />
          </div>
        </>
      )}
    </>
  );
}
