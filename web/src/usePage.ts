import { useCallback, useEffect, useRef, useState } from 'react';
import { request } from './api';
import { mergeByID, type Page, type Profile } from './types';

export function usePage<T extends { id: string | number }, C extends string | number = string>(path: string, onError: (message: string) => void) {
  const [items, setItems] = useState<T[]>([]);
  const [cursor, setCursor] = useState<C | null>(null);
  const [loading, setLoading] = useState(false);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const generation = useRef(0);
  const active = useRef<AbortController | null>(null);
  const report = useRef(onError); report.current = onError;
  const load = useCallback(async (before: C | null, reset: boolean) => {
    if (active.current && !reset) return;
    active.current?.abort();
    const controller = active.current = new AbortController();
    const expected = ++generation.current;
    setLoading(true);
    try {
      const separator = path.includes('?') ? '&' : '?';
      const page = await request<Page<T, C> & { profiles?: Profile[] }>(`${path}${before === null ? '' : `${separator}before=${encodeURIComponent(before)}`}`, { signal: controller.signal });
      if (generation.current !== expected) return;
      setItems(previous => reset ? page.items : mergeByID(previous, page.items)); setCursor(page.nextCursor);
      if (page.profiles) setProfiles(previous => reset ? page.profiles! : mergeByID(previous, page.profiles!));
    } catch (error) { if (expected === generation.current) report.current(error instanceof Error ? error.message : 'Could not load this page.'); }
    finally { if (active.current === controller) { active.current = null; setLoading(false); } }
  }, [path]);
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
