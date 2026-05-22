import { useEffect, useMemo, useState } from 'react';
import Icon from '../icons';
import { useRepos, useScopedPermissions, updateScopedPermissions } from '../api';

// 3-column drag-and-drop board for the permissions block of a single
// settings.json file. Loads BOTH settings.json and settings.local.json
// in parallel and auto-picks the one with rules so we don't show a
// blank board when rules live in the other file.

const BUCKETS = [
  { key: 'allow', label: 'Allow',  hint: 'auto-approved',        accent: 'gr', icon: 'check' },
  { key: 'ask',   label: 'Ask',    hint: 'confirm before run',   accent: 'g',  icon: 'eye' },
  { key: 'deny',  label: 'Deny',   hint: 'always blocked',       accent: 'r',  icon: 'x' },
];

const emptyPerms = () => ({ allow: [], deny: [], ask: [] });

function arraysEqual(a, b) {
  if (a === b) return true;
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}
function permsEqual(a, b) {
  return arraysEqual(a.allow, b.allow) && arraysEqual(a.deny, b.deny) && arraysEqual(a.ask, b.ask);
}
function totalCount(p) {
  return (p?.allow?.length || 0) + (p?.deny?.length || 0) + (p?.ask?.length || 0);
}

function diff(original, working) {
  const out = { added: { allow: [], deny: [], ask: [] }, removed: { allow: [], deny: [], ask: [] } };
  for (const k of ['allow', 'deny', 'ask']) {
    const o = new Set(original[k]);
    const w = new Set(working[k]);
    for (const v of working[k]) if (!o.has(v)) out.added[k].push(v);
    for (const v of original[k]) if (!w.has(v)) out.removed[k].push(v);
  }
  return out;
}

const RuleChip = ({ rule, bucket, onEdit, onDelete, onDragStart, onDragEnd }) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(rule);
  useEffect(() => setDraft(rule), [rule]);
  const commit = () => {
    const v = draft.trim();
    setEditing(false);
    if (v && v !== rule) onEdit(v);
    else if (!v) onDelete();
    else setDraft(rule);
  };
  return (
    <div
      className="pk-chip"
      draggable={!editing}
      onDragStart={(e) => { onDragStart(e); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', rule); }}
      onDragEnd={onDragEnd}
      title="Drag between columns to change bucket"
    >
      <span className="pk-grip" aria-hidden="true">⋮⋮</span>
      {editing ? (
        <input
          className="pk-chip-input mono"
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); commit(); }
            else if (e.key === 'Escape') { setDraft(rule); setEditing(false); }
          }}
        />
      ) : (
        <span className="pk-chip-text mono" onClick={() => setEditing(true)} title="Click to edit">{rule}</span>
      )}
      <button
        className="pk-chip-x"
        onClick={onDelete}
        aria-label={`Remove rule ${rule} from ${bucket}`}
        title="Delete this rule"
      >×</button>
    </div>
  );
};

const Column = ({ bucket, items, onAdd, onDrop, onRuleEdit, onRuleDelete, onDragStart, onDragEnd, isDragOver, setDragOver }) => {
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState('');
  const submit = () => {
    const v = draft.trim();
    if (v) onAdd(v);
    setDraft('');
    setAdding(false);
  };
  return (
    <div
      className={'pk-col card-frame' + (isDragOver ? ' pk-col-dragover' : '')}
      onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => { e.preventDefault(); setDragOver(false); onDrop(); }}
    >
      <div className="card-frame-head">
        <h2 className="section-title">
          <Icon name={bucket.icon} size={13} />
          {bucket.label}
        </h2>
        <span className={'bg bg-' + bucket.accent}>{items.length}</span>
      </div>
      <div className="pk-col-hint mono">{bucket.hint}</div>
      <div className="pk-col-body">
        {items.map((rule) => (
          <RuleChip
            key={rule}
            rule={rule}
            bucket={bucket.key}
            onEdit={(v) => onRuleEdit(rule, v)}
            onDelete={() => onRuleDelete(rule)}
            onDragStart={(e) => onDragStart(rule, bucket.key, e)}
            onDragEnd={onDragEnd}
          />
        ))}
        {items.length === 0 && !adding && <div className="pk-empty">drag rules here or click + to add</div>}
        {adding ? (
          <div className="pk-chip pk-chip-new">
            <span className="pk-grip" aria-hidden="true">+</span>
            <input
              className="pk-chip-input mono"
              autoFocus
              placeholder="Bash(npm test:*)"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={submit}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); submit(); }
                else if (e.key === 'Escape') { setDraft(''); setAdding(false); }
              }}
            />
          </div>
        ) : (
          <button className="pk-add-btn" onClick={() => setAdding(true)}>
            <Icon name="plus" size={11} /> Add rule
          </button>
        )}
      </div>
    </div>
  );
};

const DiffModal = ({ d, onConfirm, onCancel, target, scope, busy }) => {
  const isEmpty = ['allow', 'deny', 'ask'].every(k => d.added[k].length === 0 && d.removed[k].length === 0);
  return (
    <div className="pk-modal-backdrop" onClick={onCancel}>
      <div className="pk-modal" onClick={(e) => e.stopPropagation()}>
        <div className="pk-modal-head">
          <h3>Confirm save</h3>
          <button className="pk-modal-x" onClick={onCancel} aria-label="Close">×</button>
        </div>
        <div className="pk-modal-meta">
          Writing to <span className="mono tc">{target === 'settings' ? 'settings.json' : 'settings.local.json'}</span>
          {' '} (scope: <span className="mono">{scope}</span>)
        </div>
        <div className="pk-diff">
          {isEmpty && <div className="empty">No changes</div>}
          {['allow', 'ask', 'deny'].map((k) => (
            <div key={k} className="pk-diff-bucket">
              {(d.added[k].length > 0 || d.removed[k].length > 0) && (
                <div className="pk-diff-label mono tm">{k}/</div>
              )}
              {d.added[k].map((r) => <div key={'+' + r} className="pk-diff-add mono">+ {r}</div>)}
              {d.removed[k].map((r) => <div key={'-' + r} className="pk-diff-del mono">- {r}</div>)}
            </div>
          ))}
        </div>
        <div className="pk-modal-actions">
          <button className="btn" onClick={onCancel}>Cancel</button>
          <button className="btn primary" onClick={onConfirm} disabled={isEmpty || busy}>
            {busy ? 'Saving…' : 'Confirm save'}
          </button>
        </div>
      </div>
    </div>
  );
};

const PermissionsKanban = ({ defaultScope = 'global' }) => {
  const { data: repos } = useRepos();
  const [scope, setScope] = useState(defaultScope);
  // `target` starts as null → auto-pick once both file fetches return.
  // Once the user clicks a segment, manualPick flips and locks the target.
  const [target, setTarget] = useState(null);
  const [manualPick, setManualPick] = useState(false);

  // Fetch both files in parallel — counts feed both auto-pick and the segment labels.
  const { data: localServer } = useScopedPermissions(scope, 'settings_local');
  const { data: commitServer } = useScopedPermissions(scope, 'settings');
  const activeServer = target === 'settings' ? commitServer : localServer;

  // Reset auto-pick whenever the scope changes — the new repo may have rules
  // in a different file.
  useEffect(() => { setManualPick(false); setTarget(null); }, [scope]);

  // Auto-pick: whichever file has more rules wins. Tie → settings_local
  // (the safer default for new edits).
  useEffect(() => {
    if (manualPick) return;
    if (!localServer || !commitServer) return;
    const localN = totalCount(localServer.permissions);
    const commitN = totalCount(commitServer.permissions);
    setTarget(commitN > localN ? 'settings' : 'settings_local');
  }, [manualPick, localServer?.mtime, commitServer?.mtime, localServer?.fileExists, commitServer?.fileExists]);  // eslint-disable-line react-hooks/exhaustive-deps

  const pickTarget = (t) => { setManualPick(true); setTarget(t); };

  // Working state — what the user is editing, before save.
  const [working, setWorking] = useState(emptyPerms());
  const [original, setOriginal] = useState(emptyPerms());
  const [serverMtime, setServerMtime] = useState(0);

  const [dragOverKey, setDragOverKey] = useState(null);
  const [draggedFrom, setDraggedFrom] = useState(null);
  const [draggedRule, setDraggedRule] = useState(null);

  const [showDiff, setShowDiff] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');

  // Sync the active server response into working state.
  useEffect(() => {
    if (!activeServer || !activeServer.permissions) return;
    const snap = {
      allow: [...activeServer.permissions.allow],
      deny:  [...activeServer.permissions.deny],
      ask:   [...activeServer.permissions.ask],
    };
    setOriginal(snap);
    setWorking({ allow: [...snap.allow], deny: [...snap.deny], ask: [...snap.ask] });
    setServerMtime(activeServer.mtime || 0);
    setError('');
  }, [activeServer?.scope, activeServer?.target, activeServer?.mtime, activeServer?.fileExists]);  // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = useMemo(() => !permsEqual(working, original), [working, original]);
  const d = useMemo(() => diff(original, working), [original, working]);

  const mutate = (fn) => setWorking((cur) => {
    const next = { allow: [...cur.allow], deny: [...cur.deny], ask: [...cur.ask] };
    fn(next);
    return next;
  });
  const handleAdd = (bucket, rule) => mutate((w) => {
    if (!w[bucket].includes(rule)) w[bucket].push(rule);
  });
  const handleDelete = (bucket, rule) => mutate((w) => {
    w[bucket] = w[bucket].filter((r) => r !== rule);
  });
  const handleEdit = (bucket, oldRule, newRule) => mutate((w) => {
    const idx = w[bucket].indexOf(oldRule);
    if (idx >= 0) {
      if (w[bucket].includes(newRule) && newRule !== oldRule) {
        w[bucket].splice(idx, 1);
      } else {
        w[bucket][idx] = newRule;
      }
    }
  });
  const handleDrop = (toBucket) => {
    if (!draggedRule || !draggedFrom) return;
    if (draggedFrom === toBucket) return;
    mutate((w) => {
      w[draggedFrom] = w[draggedFrom].filter((r) => r !== draggedRule);
      if (!w[toBucket].includes(draggedRule)) w[toBucket].push(draggedRule);
    });
    setDraggedRule(null);
    setDraggedFrom(null);
  };

  const handleSave = async () => {
    if (!target) return;
    setSaving(true);
    setError('');
    try {
      const result = await updateScopedPermissions({
        scope, target,
        permissions: working,
        ifUnchangedSince: serverMtime || null,
      });
      setOriginal({ allow: [...working.allow], deny: [...working.deny], ask: [...working.ask] });
      setServerMtime(result.mtime);
      setShowDiff(false);
      setToast(result.backupPath ? `Saved. Backup: ${result.backupPath.split('/').pop()}` : 'Saved.');
      setTimeout(() => setToast(''), 3000);
    } catch (e) {
      if (e.stale) {
        setError('File changed on disk. Discard local changes and reload to continue.');
      } else {
        setError(e.message || String(e));
      }
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setWorking({ allow: [...original.allow], deny: [...original.deny], ask: [...original.ask] });
    setError('');
  };

  const repoOptions = useMemo(() => {
    const rs = (repos || []).filter((r) => r && r.id && r.id !== 'global');
    return [{ id: 'global', name: 'Global (~/.claude)' }, ...rs];
  }, [repos]);

  const localCount = totalCount(localServer?.permissions);
  const commitCount = totalCount(commitServer?.permissions);
  const totalChanges = ['allow', 'deny', 'ask'].reduce((n, k) => n + d.added[k].length + d.removed[k].length, 0);
  const activeFilePath = activeServer?.filePath || '';
  const activeFileExists = !!activeServer?.fileExists;

  return (
    <div className="pk-root">
      <div className="pk-toolbar">
        <div className="row gap-sm">
          <label className="pk-toolbar-label">Scope</label>
          <select className="pk-select mono" value={scope} onChange={(e) => setScope(e.target.value)}>
            {repoOptions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </div>
        <div className="row gap-sm">
          <label className="pk-toolbar-label">File</label>
          <div className="pk-segmented">
            <button
              className={'pk-segment' + (target === 'settings_local' ? ' active' : '')}
              onClick={() => pickTarget('settings_local')}
              title="Edits go to the gitignored settings.local.json (safer)"
            >
              settings.local.json{localCount > 0 ? ` (${localCount})` : ''}
            </button>
            <button
              className={'pk-segment' + (target === 'settings' ? ' active' : '')}
              onClick={() => pickTarget('settings')}
              title="Edits go to the committed settings.json"
            >
              settings.json{commitCount > 0 ? ` (${commitCount})` : ''}
            </button>
          </div>
        </div>
        <div className="pk-toolbar-spacer" />
        <button className="btn" onClick={handleReset} disabled={!dirty || saving}>
          <Icon name="x" size={11} /> Reset
        </button>
        <button className="btn primary" onClick={() => setShowDiff(true)} disabled={!dirty || saving || !target}>
          <Icon name="check" size={11} /> Save{totalChanges > 0 ? ` (${totalChanges})` : ''}
        </button>
      </div>

      <div className="pk-meta mono">
        {target == null
          ? 'Resolving…'
          : activeFileExists
            ? <>File: <span className="tc">{activeFilePath}</span></>
            : activeFilePath
              ? <>File doesn't exist yet — will be created on first save: <span className="tm">{activeFilePath}</span></>
              : <>Scope <span className="tm">{scope}</span> not recognized by the backend. Restart the backend so it picks up the new /api/permissions/scoped route.</>}
      </div>

      {error && <div className="pk-error mono">{error}</div>}
      {toast && <div className="pk-toast mono">{toast}</div>}

      <div className="pk-board">
        {BUCKETS.map((b) => (
          <Column
            key={b.key}
            bucket={b}
            items={working[b.key]}
            onAdd={(rule) => handleAdd(b.key, rule)}
            onRuleEdit={(oldR, newR) => handleEdit(b.key, oldR, newR)}
            onRuleDelete={(rule) => handleDelete(b.key, rule)}
            onDragStart={(rule, from) => { setDraggedRule(rule); setDraggedFrom(from); }}
            onDragEnd={() => { setDraggedRule(null); setDraggedFrom(null); }}
            onDrop={() => handleDrop(b.key)}
            isDragOver={dragOverKey === b.key}
            setDragOver={(on) => setDragOverKey(on ? b.key : null)}
          />
        ))}
      </div>

      {showDiff && (
        <DiffModal
          d={d}
          scope={scope}
          target={target}
          busy={saving}
          onCancel={() => setShowDiff(false)}
          onConfirm={handleSave}
        />
      )}
    </div>
  );
};

export default PermissionsKanban;
