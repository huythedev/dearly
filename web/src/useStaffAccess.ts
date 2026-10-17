import { useCallback, useEffect, useState } from 'react';
import { APIError, request } from './api';
import { hasStaffPermission, staffScope, type StaffClaims } from './permissions';
import type { Dearly } from './useDearly';

export interface StaffAccess extends StaffClaims { userID: string }

export function useStaffAccess(store: Dearly) {
  const state = store.envelope!.state;
  const userID = state.currentUserID;
  const scope = staffScope(state);
  const allowed = hasStaffPermission(state, 'reports.read');
  const [access, setAccess] = useState<StaffAccess | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const refresh = store.refresh;
  const deny = useCallback((error: APIError) => {
    setAccess(null); setFailure(error.message);
    void refresh(true);
  }, [refresh]);

  useEffect(() => {
    let active = true;
    let controller: AbortController | null = null;
    let generation = 0;
    const verify = async () => {
      controller?.abort();
      const expected = ++generation;
      setAccess(null); setFailure(null);
      if (!allowed) return;
      const current = controller = new AbortController();
      try {
        const access = await request<StaffAccess>('staff/access', { signal: current.signal, headers: { 'X-Dearly-User': userID } });
        if (!active || expected !== generation || current.signal.aborted) return;
        if (access.userID !== userID || !hasStaffPermission(access, 'reports.read')) {
          throw new APIError(403, 'You do not have access to management.');
        }
        setAccess(access);
        // A cached admin snapshot must not preserve controls after a server-side demotion.
        if (staffScope(access) !== scope) void refresh(true);
      } catch (error) {
        if (!active || expected !== generation || current.signal.aborted) return;
        setFailure(error instanceof Error ? error.message : 'Could not sync.');
        if (error instanceof APIError && [401, 403, 409].includes(error.status)) deny(error);
      }
    };
    const visible = () => { if (document.visibilityState === 'visible') void verify(); };
    const restored = (event: PageTransitionEvent) => { if (event.persisted) void verify(); };
    void verify();
    window.addEventListener('pageshow', restored);
    document.addEventListener('visibilitychange', visible);
    return () => {
      active = false; controller?.abort();
      window.removeEventListener('pageshow', restored);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [userID, scope, allowed, attempt, refresh, deny]);

  return { access: allowed && access?.userID === userID ? access : null, failure,
    denied: !allowed, deny, retry: () => setAttempt(value => value + 1) };
}
