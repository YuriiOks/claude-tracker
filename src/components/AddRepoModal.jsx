import { useState } from 'react';
import Icon from '../icons';
import { useRepoCandidates, addRepo } from '../api';

const AddRepoModal = ({ onClose, onAdded }) => {
  const { data: candidates, loading } = useRepoCandidates();
  const [manualPath, setManualPath] = useState('');
  const [adding, setAdding] = useState(null);  // path currently being added
  const [error, setError] = useState(null);

  const handleAdd = async (hostPath) => {
    setAdding(hostPath);
    setError(null);
    try {
      await addRepo(hostPath);
      if (onAdded) onAdded(hostPath);
    } catch (e) {
      setError(e.message || 'Failed to add repo');
    } finally {
      setAdding(null);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2 className="section-title"><Icon name="plug" />Add a repo to track</h2>
          <button className="icon-btn" onClick={onClose} title="Close"><Icon name="x" /></button>
        </div>

        <div className="modal-body">
          <p className="modal-sub">
            Discovered from <span className="mono">~/.claude/projects/</span> — only paths that
            still exist and contain a <span className="mono">.claude/</span> folder are shown.
          </p>

          {loading && <div className="empty">Scanning…</div>}

          {!loading && (!candidates || candidates.length === 0) && (
            <div className="empty">
              No candidate repos found. Try the manual path field below.
            </div>
          )}

          {!loading && candidates && candidates.length > 0 && (
            <div className="list">
              {candidates.map((c) => (
                <div
                  key={c.hostPath}
                  className="list-row"
                  style={{ display: 'grid', gridTemplateColumns: '1fr auto auto' }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div className="tb">{c.name}</div>
                    <div className="mono" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.hostPath}</div>
                  </div>
                  <span className="bg bg-m">{c.sessions} sessions</span>
                  {c.alreadyTracked ? (
                    <span className="bg bg-gr"><Icon name="check" size={10} />tracked</span>
                  ) : (
                    <button
                      className="btn primary"
                      style={{ padding: '.35rem .8rem', fontSize: '.74rem' }}
                      disabled={adding === c.hostPath}
                      onClick={() => handleAdd(c.hostPath)}
                    >
                      {adding === c.hostPath ? 'Adding…' : 'Add'}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          <div className="modal-section">
            <div className="section-title" style={{ fontSize: '.74rem' }}>Or enter a path manually</div>
            <div className="row gap-sm" style={{ marginTop: '.5rem' }}>
              <input
                type="text"
                className="modal-input"
                placeholder="/Users/you/path/to/repo"
                value={manualPath}
                onChange={(e) => setManualPath(e.target.value)}
              />
              <button
                className="btn primary"
                disabled={!manualPath.trim() || adding === manualPath}
                onClick={() => handleAdd(manualPath.trim())}
              >
                {adding === manualPath ? 'Adding…' : 'Add'}
              </button>
            </div>
          </div>

          {error && (
            <div className="modal-error" role="alert">
              <Icon name="x" size={11} /> {error}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AddRepoModal;
