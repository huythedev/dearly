import { afterEach, describe, expect, it, vi } from 'vitest';
import { command, request, sendCommand } from './api';
import { fromSwift, gardenStage, mergeByID, utcDay, type Connection } from './types';

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('wire contract', () => {
  it('converts Swift dates and UTC day boundaries without using local timezone', () => {
    expect(fromSwift(0).toISOString()).toBe('2001-01-01T00:00:00.000Z');
    expect(utcDay(813585600)).toBe('2026-10-13');
  });
  it('merges retried messages by id, keeping the authoritative value', () => {
    expect(mergeByID([{ id: 'a', text: 'old' }, { id: 'b', text: 'second' }], [{ id: 'a', text: 'new' }]))
      .toEqual([{ id: 'a', text: 'new' }, { id: 'b', text: 'second' }]);
  });
  it('uses persistent garden rewards rather than a reset current streak', () => {
    expect(gardenStage({ bestStreak: 14, serverTotalDays: 20, serverCurrentStreak: 0 } as Connection)).toBe(4);
    expect(gardenStage({ bestStreak: 2, serverTotalDays: 30 } as Connection)).toBe(5);
  });
  it('retries a lost mutation reply using the same key and same-origin credentials', async () => {
    vi.stubGlobal('localStorage', { getItem: () => 'vi' });
    const fetch = vi.fn().mockRejectedValueOnce(new TypeError('Lost reply')).mockResolvedValueOnce(new Response('{"ok":true,"id":"saved"}'));
    vi.stubGlobal('fetch', fetch);
    const value = command('message.send', { connectionID: 'connection', text: 'Hello' });
    await expect(sendCommand(value, undefined, 'first-account')).resolves.toEqual({ ok: true, id: 'saved' });
    expect(fetch.mock.calls[0][0]).toBe('/v1/actions');
    expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[1][1].body);
    expect(fetch.mock.calls[0][1].credentials).toBe('same-origin');
    expect(fetch.mock.calls[0][1].headers.get('X-Dearly-Client')).toBe('web');
    expect(fetch.mock.calls[0][1].headers.get('Accept-Language')).toBe('vi');
    expect(fetch.mock.calls[0][1].headers.get('X-Dearly-User')).toBe('first-account');
    expect(fetch.mock.calls[1][1].headers.get('X-Dearly-User')).toBe('first-account');
    expect(fetch.mock.calls[0][1].headers.has('Authorization')).toBe(false);
  });
  it('does not retry a validation or permission failure', async () => {
    vi.stubGlobal('localStorage', { getItem: () => 'en' });
    const fetch = vi.fn().mockResolvedValue(new Response('{"detail":"Not allowed"}', { status: 403 }));
    vi.stubGlobal('fetch', fetch);
    await expect(sendCommand(command('message.send', {}))).rejects.toThrow('Not allowed');
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('never retries a mutation cancelled by a session change', async () => {
    vi.stubGlobal('localStorage', { getItem: () => 'en' });
    const controller = new AbortController();
    const fetch = vi.fn().mockImplementation(async () => {
      controller.abort();
      throw new TypeError('Lost reply');
    });
    vi.stubGlobal('fetch', fetch);
    await expect(sendCommand(command('journal.save', {}), controller.signal)).rejects.toThrow('Lost reply');
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('keeps a deadline while reading the body with an external cancellation signal', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('localStorage', { getItem: () => 'en' });
    vi.stubGlobal('fetch', async (_path: string, options: RequestInit) => ({
      ok: true,
      status: 200,
      json: () => new Promise((_resolve, reject) => options.signal!.addEventListener('abort', () => reject(options.signal!.reason))),
    }));
    const result = expect(request('journals', { signal: new AbortController().signal })).rejects.toThrow('Request timed out.');
    await vi.advanceTimersByTimeAsync(15000);
    await result;
    expect(vi.getTimerCount()).toBe(0);
  });
});
