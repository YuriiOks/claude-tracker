// Extracted from TweaksPanel.jsx so the heavy panel UI can be lazy-loaded
// while the lightweight state hook stays in the eager bundle.
import { useState, useCallback } from 'react';

// `init(defaults)` is an optional lazy initializer -- e.g. hydrating a key
// from localStorage -- so callers can override part of `defaults` on first
// render without a render-then-overwrite flash. Runs once (React lazy
// useState init), returns a partial object merged over `defaults`.
export function useTweaks(defaults, init) {
  const [values, setValues] = useState(() => (init ? { ...defaults, ...init(defaults) } : defaults));
  const setTweak = useCallback((keyOrEdits, val) => {
    const edits = typeof keyOrEdits === 'object' && keyOrEdits !== null
      ? keyOrEdits : { [keyOrEdits]: val };
    setValues((prev) => ({ ...prev, ...edits }));
  }, []);
  return [values, setTweak];
}
