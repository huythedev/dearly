import { useCallback, useEffect, useRef, useState } from 'react';
import { APIError, request } from './api';
import { mergeByID, type Page, type Profile } from './types';

export function usePage<T extends { id: string | number }, C extends string | number = string>(path: string, onError: (message: string) => void,
  options?: { userID: string; onDenied: (error: APIError) => void }) {
  const [items, setItems] = useState<T[]>([]);
  const [cursor, setCursor] = useState<C | null>(null);
  const [loading, setLoading] = useState(false);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const generation = useRef(0);
  const active = useRef<AbortController | null>(null);
  const report = useRef(onError); report.current = onError;
  const denied = useRef(options?.onDenied); denied.current = options?.onDenied;
  const userID = options?.userID;
  const load = useCallback(async (before: C | null, reset: boolean) => {
    if (active.current && !reset) return;
    active.current?.abort();
    const controller = active.current = new AbortController();
    const expected = ++generation.current;
    setLoading(true);
    try {
      const separator = path.includes('?') ? '&' : '?';
      const page = await request<Page<T, C> & { profiles?: Profile[] }>(`${path}${before === null ? '' : `${separator}before=${encodeURIComponent(before)}`}`, {
        signal: controller.signal, headers: userID ? { 'X-Dearly-User': userID } : undefined,
      });
      if (generation.current !== expected) return;
      setItems(previous => reset ? page.items : mergeByID(previous, page.items)); setCursor(page.nextCursor);
      if (page.profiles) setProfiles(previous => reset ? page.profiles! : mergeByID(previous, page.profiles!));
    } catch (error) {
      if (expected !== generation.current || controller.signal.aborted) return;
      if (error instanceof APIError && [401, 403, 409].includes(error.status)) {
        setItems([]); setCursor(null); setProfiles([]);
        if (denied.current) { denied.current(error); return; }
      }
      report.current(error instanceof Error ? error.message : 'Could not load this page.');
    }
    finally { if (active.current === controller) { active.current = null; setLoading(false); } }
  }, [path, userID]);
  const reload = useCallback(() => {
    setItems([]); setCursor(null); setProfiles([]);
    return load(null, true);
  }, [load]);
  useEffect(() => {
    void reload();
    return () => { generation.current++; active.current?.abort(); active.current = null; };
  }, [reload]);
  return { items, cursor, profiles, loading, reload, more: () => { if (cursor !== null && !loading) void load(cursor, false); } };
}
