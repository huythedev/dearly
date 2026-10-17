import { useCallback, useEffect, useRef, useState } from 'react';
import { APIError, command, fetchState, request, sendCommand } from './api';
import { ChatTransport, type ChatStatus } from './chat';
import { RefreshQueue } from './synchronization';
import { activeConnection, mergeByID, type Envelope } from './types';

export function useDearly() {
  const [envelope, setEnvelope] = useState<Envelope | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [syncError, setSyncError] = useState(false);
  const [chatStatus, setChatStatus] = useState<ChatStatus>('connecting');
  const generation = useRef(0);
  const etag = useRef<string | null>(null);
  const queue = useRef<RefreshQueue | null>(null);
  const operation = useRef<AbortController | null>(null);
  const chat = useRef<ChatTransport | null>(null);

  const expire = useCallback(() => {
    generation.current++;
    etag.current = null;
    queue.current?.invalidate();
    operation.current?.abort();
    operation.current = null;
    chat.current?.close();
    chat.current = null;
    setEnvelope(null);
    setBusy(false);
    setLoading(false);
    setSyncError(false);
  }, []);

  if (!queue.current) queue.current = new RefreshQueue(async (force, signal) => {
    const expected = generation.current;
    const current = () => expected === generation.current && !signal.aborted;
    try {
      const result = await fetchState(force ? null : etag.current, signal);
      if (!current()) return;
      etag.current = result.etag;
      if (result.envelope) {
        const updated = result.envelope;
        setEnvelope(previous => {
          if (!current()) return previous;
          const connection = activeConnection(updated.state);
          const messages = connection && previous?.state.currentUserID === updated.state.currentUserID
            ? mergeByID(previous.state.messages.filter(m => m.connectionID === connection.id), updated.state.messages)
              .sort((a, b) => a.date - b.date || a.id.localeCompare(b.id)).slice(-500)
            : updated.state.messages;
          return { ...updated, state: { ...updated.state, messages } };
        });
      }
      setSyncError(false);
    } catch (error) {
      if (!current()) return;
      if (error instanceof APIError && error.status === 401) expire();
      else setSyncError(true);
    } finally { if (current()) setLoading(false); }
  });

  const refresh = useCallback((force = false) => queue.current!.request(force), []);
  useEffect(() => {
    void refresh(true);
    return () => { queue.current?.invalidate(); operation.current?.abort(); };
  }, [refresh]);

  const userID = envelope?.state.currentUserID;
  useEffect(() => {
    if (!userID) return;
    const expected = generation.current;
    let active = true;
    const current = () => active && expected === generation.current;
    const transport = new ChatTransport({
      status: status => { if (current()) setChatStatus(status); },
      changed: () => { if (current()) void refresh(true); },
      sessionRejected: () => { if (current()) void refresh(true); },
      message: message => setEnvelope(previous => {
        if (!current() || !previous || activeConnection(previous.state)?.id !== message.connectionID) return previous;
        return { ...previous, state: { ...previous.state, messages: mergeByID(previous.state.messages, [message])
          .sort((a, b) => a.date - b.date || a.id.localeCompare(b.id)).slice(-500) } };
      }),
    });
    chat.current = transport;
    setChatStatus('connecting');
    const sync = () => { if (current() && document.visibilityState === 'visible') void refresh(); };
    const interval = setInterval(sync, 15000);
    document.addEventListener('visibilitychange', sync);
    window.addEventListener('online', sync);
    return () => {
      active = false;
      transport.close();
      if (chat.current === transport) chat.current = null;
      clearInterval(interval);
      document.removeEventListener('visibilitychange', sync);
      window.removeEventListener('online', sync);
    };
  }, [userID, refresh, expire]);

  const run = async (perform: (signal: AbortSignal) => Promise<unknown>, onDenied?: (error: APIError) => void) => {
    if (operation.current) return false;
    const controller = operation.current = new AbortController();
    const expected = generation.current;
    const current = () => expected === generation.current && !controller.signal.aborted;
    setBusy(true); setError('');
    try { await perform(controller.signal); return current(); }
    catch (error) {
      if (!current()) return false;
      if (error instanceof APIError && [401, 403, 409].includes(error.status)) onDenied?.(error);
      if (error instanceof APIError && error.status === 401) expire();
      setError(error instanceof Error ? error.message : 'Something went wrong. Please try again.');
      return false;
    } finally {
      if (operation.current === controller) { operation.current = null; setBusy(false); }
    }
  };

  return {
    envelope, loading, busy, error, syncError, chatStatus, refresh, setError,
    authenticate: (signup: boolean, fields: Record<string, string>) => {
      if (operation.current) return Promise.resolve(false);
      expire();
      return run(async signal => {
        await request(`auth/${signup ? 'register' : 'login'}`, { method: 'POST', body: JSON.stringify(fields), signal });
        if (!signal.aborted) await refresh(true);
      });
    },
    logout: async () => {
      const okay = await run(signal => request('auth/logout', { method: 'POST', signal }));
      if (okay) expire();
      return okay;
    },
    act: (kind: string, payload: Record<string, unknown>, onDenied?: (error: APIError) => void) => run(async signal => {
      const userID = envelope?.state.currentUserID;
      if (!userID) throw new APIError(401, 'Please log in.');
      const value = command(kind, payload);
      if (kind === 'message.send' && chat.current) {
        try { await chat.current.send(value); }
        catch (error) {
          if (signal.aborted || (error instanceof APIError && ![401, 503].includes(error.status))) throw error;
          await sendCommand(value, signal, userID);
        }
      } else await sendCommand(value, signal, userID);
      if (!signal.aborted) await refresh(true);
    }, onDenied),
  };
}

export type Dearly = ReturnType<typeof useDearly>;
