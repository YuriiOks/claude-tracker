import { useEffect, useMemo, useRef, useState } from 'react';
import Icon from '../icons';
import { useAgents } from '../api';
import { ROUTES } from '../routes';

// R-UX-7: ⌘K / Ctrl+K jump list over routes + tracked repos (+ agents/skills
// while open). Round 1 left the search box decorative — this makes it a
// minimal working combobox with no new dependency.

// Mounted only while the palette is open, so useAgents() (and its network
// request in real mode) never fires on every page load — just while someone
// is actually searching. Reports its filtered matches up via onResults.
function AgentResults({ query, onResults }) {
  const { data } = useAgents();
  useEffect(() => {
    const q = query.trim().toLowerCase();
    if (!q || !data) { onResults([]); return; }
    const items = Object.entries(data)
      .filter(([name]) => name.toLowerCase().includes(q))
      .slice(0, 8)
      .map(([name, meta]) => ({
        type: 'agent',
        key: `agent:${name}`,
        label: name,
        sub: meta?.role || meta?.repo || 'agent',
        route: { page: 'agent', name, kind: 'agent', repoId: meta?.repo || null },
      }));
    onResults(items);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, data]);
  return null;
}

export default function CommandPalette({ repos = [], setRoute }) {
  const [open, setOpen] = useState(false);

  // Global ⌘K / Ctrl+K opens the palette from anywhere on desktop.
  useEffect(() => {
    const onKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen(true);
      } else if (e.key === 'Escape' && open) {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open]);

  return (
    <>
      <button type="button" className="search-box" onClick={() => setOpen(true)} aria-label="Open command palette">
        <Icon name="search" size={12} />
        <span className="search-box-placeholder">Search agents, skills, files…</span>
        <kbd>⌘K</kbd>
      </button>
      {/* Mounted fresh on every open (and unmounted on close) so query/
          activeIndex reset naturally via initial useState — no "sync state
          from a prop change" effect needed. */}
      {open && <PaletteBody repos={repos} setRoute={setRoute} onClose={() => setOpen(false)} />}
    </>
  );
}

function PaletteBody({ repos, setRoute, onClose }) {
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [agentItems, setAgentItems] = useState([]);
  const inputRef = useRef(null);

  // Focus on mount (imperative DOM call, not setState — no cascading-render
  // warning) so the just-opened input is immediately typeable.
  useEffect(() => { inputRef.current?.focus(); }, []);

  const routeItems = useMemo(() => ROUTES.map(r => ({
    type: 'route',
    key: `route:${r.id}`,
    label: r.label,
    icon: r.icon,
    route: { page: r.id },
  })), []);

  const repoItems = useMemo(() => repos.map(r => ({
    type: 'repo',
    key: `repo:${r.id}`,
    label: r.name || r.id,
    sub: 'repo',
    route: { page: 'repo', repoId: r.id },
  })), [repos]);

  const items = useMemo(() => {
    const q = query.trim().toLowerCase();
    const base = [...routeItems, ...repoItems];
    const filtered = q ? base.filter(i => i.label.toLowerCase().includes(q)) : base.slice(0, 8);
    return q ? [...filtered, ...agentItems] : filtered;
  }, [query, routeItems, repoItems, agentItems]);

  // Clamp instead of re-syncing via effect: activeIndex only ever moves by
  // explicit user action (typing resets it inline below, arrows/hover set it
  // directly), so a derived clamp at render time is enough to keep it valid
  // when the list shrinks.
  const safeIndex = Math.min(activeIndex, Math.max(items.length - 1, 0));

  const pick = (item) => {
    if (!item) return;
    setRoute(item.route);
    onClose();
  };

  const onChangeQuery = (e) => {
    setQuery(e.target.value);
    setActiveIndex(0);
  };

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex(Math.min(safeIndex + 1, items.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex(Math.max(safeIndex - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      pick(items[safeIndex]);
    } else if (e.key === 'Escape') {
      onClose();
    }
  };

  return (
    <>
      <AgentResults query={query} onResults={setAgentItems} />
      <div className="cmdk-overlay" onMouseDown={onClose}>
        <div
          className="cmdk-panel"
          role="combobox"
          aria-expanded="true"
          aria-owns="cmdk-listbox"
          aria-haspopup="listbox"
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div className="cmdk-input-row">
            <Icon name="search" size={13} />
            <input
              ref={inputRef}
              value={query}
              onChange={onChangeQuery}
              onKeyDown={onKeyDown}
              placeholder="Jump to a page, repo, agent…"
              aria-autocomplete="list"
              aria-controls="cmdk-listbox"
              aria-activedescendant={items[safeIndex] ? `cmdk-opt-${safeIndex}` : undefined}
            />
            <kbd>Esc</kbd>
          </div>
          <ul className="cmdk-list" role="listbox" id="cmdk-listbox">
            {items.length === 0 && <li className="cmdk-empty">No matches</li>}
            {items.map((item, i) => (
              <li
                key={item.key}
                id={`cmdk-opt-${i}`}
                role="option"
                aria-selected={i === safeIndex}
                className={'cmdk-item' + (i === safeIndex ? ' active' : '')}
                onMouseEnter={() => setActiveIndex(i)}
                onMouseDown={(e) => { e.preventDefault(); pick(item); }}
              >
                {item.icon && <Icon name={item.icon} size={13} />}
                <span className="cmdk-item-label">{item.label}</span>
                {item.sub && <span className="cmdk-item-sub">{item.sub}</span>}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}
