// Tiny shared time formatters. Both LiveAgents and DiffPage render
// "N seconds/minutes/hours ago" labels; this is the single source of
// truth for that string so the dashboard reads consistently.

// fmtSince(seconds): "now" | "Ns ago" | "Nm ago" | "Nh ago"
// Returns "—" for null/undefined so a missing value never crashes a row.
export function fmtSince(s) {
  if (s == null) return '—';
  if (s < 1) return 'now';
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m ago` : `${Math.floor(m / 60)}h ago`;
}

// fmtAgo(isoTs): smart relative-time. Sub-day ages use fmtSince ("3m ago",
// "5h ago"); older items switch to a compact local-date label ("May 10",
// "Apr 30 2025" if cross-year) so a 30-hour-old row doesn't read as "30h
// ago" when "May 10" is clearer. Returns "—" for missing/invalid input.
const _MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
export function fmtAgo(isoTs) {
  if (!isoTs) return '—';
  const t = new Date(isoTs).getTime();
  if (Number.isNaN(t)) return '—';
  const secs = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (secs < 86400) return fmtSince(secs);
  const d = new Date(t);
  const sameYear = d.getFullYear() === new Date().getFullYear();
  const label = `${_MONTHS[d.getMonth()]} ${d.getDate()}`;
  return sameYear ? label : `${label} ${d.getFullYear()}`;
}
