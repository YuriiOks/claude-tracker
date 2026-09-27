import { useEffect } from 'react';
import { setAuthToken } from './api';

// Captures `?pair=<token>` from the URL on first load (the link a paired
// phone opens), persists it via api.js's setAuthToken so every subsequent
// fetch/WS call attaches it, then strips the param from the address bar so
// it doesn't linger in history/bookmarks. See the AUTH CONTRACT: requests
// from localhost need no token, everything else does.
export function usePairing() {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const pair = params.get('pair');
    if (!pair) return;
    setAuthToken(pair);
    params.delete('pair');
    const qs = params.toString();
    const url = window.location.pathname + (qs ? `?${qs}` : '') + window.location.hash;
    window.history.replaceState({}, '', url);
  }, []);
}
