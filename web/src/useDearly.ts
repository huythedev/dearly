import { useCallback, useEffect, useRef, useState } from 'react';
import { APIError, command, fetchState, request, sendCommand } from './api';
import { ChatTransport, type ChatStatus } from './chat';
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
  const inflight = useRef<Promise<void> | null>(null);
  const chat = useRef<ChatTransport | null>(null);

  const expire = useCallback(() => {
    generation.current++; etag.current = null; setEnvelope(null); setBusy(false);
  }, []);

  const refresh = useCallback(async (force = false) => {
    if (inflight.current) {
      await inflight.current;
      if (!force) return;
    }
    const expected = generation.current;
    const operation = (async () => {
      try {
        const result = await fetchState(force ? null : etag.current);
        if (expected !== generation.current) return;
        etag.current = result.etag;
        if (result.envelope) {
          const updated = result.envelope;
          setEnvelope(previous => {
            const connection = activeConnection(updated.state);
            if (connection && previous?.state.currentUserID === updated.state.currentUserID) {
              updated.state.messages = mergeByID(previous.state.messages.filter(m => m.connectionID === connection.id), updated.state.messages)
                .sort((a, b) => a.date - b.date || a.id.localeCompare(b.id)).slice(-500);
            }
            return updated;
          });
        }
        setSyncError(false);
      } catch (error) {
        if (expected !== generation.current) return;
        if (error instanceof APIError && error.status === 401) expire();
        else setSyncError(true);
      } finally { setLoading(false); }
    })();
    inflight.current = operation;
    await operation;
    if (inflight.current === operation) inflight.current = null;
  }, [expire]);

  useEffect(() => { void refresh(); }, [refresh]);
  const userID = envelope?.state.currentUserID;
  useEffect(() => {
    if (!userID) return;
    const transport = new ChatTransport({
      status: setChatStatus, changed: () => { void refresh(); }, expired: expire,
      message: message => setEnvelope(previous => {
        if (!previous || activeConnection(previous.state)?.id !== message.connectionID) return previous;
        return { ...previous, state: { ...previous.state, messages: mergeByID(previous.state.messages, [message])
          .sort((a, b) => a.date - b.date || a.id.localeCompare(b.id)).slice(-500) } };
      }),
    });
    chat.current = transport;
    const sync = () => { if (document.visibilityState === 'visible') void refresh(); };
    const interval = setInterval(sync, 15000);
    document.addEventListener('visibilitychange', sync);
    window.addEventListener('online', sync);
    return () => {
      transport.close(); chat.current = null; clearInterval(interval);
      document.removeEventListener('visibilitychange', sync); window.removeEventListener('online', sync);
    };
  }, [userID, refresh, expire]);

  const run = async (operation: () => Promise<unknown>) => {
    setBusy(true); setError('');
    try { await operation(); return true; }
    catch (error) {
      if (error instanceof APIError && error.status === 401) expire();
      setError(error instanceof Error ? error.message : 'Something went wrong. Please try again.');
      return false;
    } finally { setBusy(false); }
  };

  return {
    envelope, loading, busy, error, syncError, chatStatus, refresh, setError,
    authenticate: (signup: boolean, fields: Record<string, string>) => run(async () => {
      await request(`auth/${signup ? 'register' : 'login'}`, { method: 'POST', body: JSON.stringify(fields) });
      generation.current++; etag.current = null; await refresh(true);
    }),
    logout: () => run(async () => { await request('auth/logout', { method: 'POST' }); expire(); }),
    act: (kind: string, payload: Record<string, unknown>) => run(async () => {
      const value = command(kind, payload);
      if (kind === 'message.send' && chat.current) {
        try { await chat.current.send(value); }
        catch (error) {
          if (error instanceof APIError && error.status !== 503) throw error;
          await sendCommand(value);
        }
      } else await sendCommand(value);
      await refresh(true);
    }),
  };
}

export type Dearly = ReturnType<typeof useDearly>;
