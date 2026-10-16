import { describe, expect, it } from 'vitest';
import { RefreshQueue } from './synchronization';

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>(done => { resolve = done; });
  return { promise, resolve };
}

describe('snapshot synchronization', () => {
  it('serializes reads and coalesces invalidations into a fresh follow-up', async () => {
    const reads: { force: boolean; signal: AbortSignal; gate: ReturnType<typeof deferred> }[] = [];
    let active = 0, peak = 0;
    const queue = new RefreshQueue(async (force, signal) => {
      active++; peak = Math.max(peak, active);
      const gate = deferred(); reads.push({ force, signal, gate });
      await gate.promise; active--;
    });
    const initial = queue.request();
    void queue.request();
    void queue.request(true);
    void queue.request(true);
    expect(reads).toHaveLength(1);
    reads[0].gate.resolve();
    await Promise.resolve(); await Promise.resolve();
    expect(reads).toHaveLength(2);
    expect(reads[1].force).toBe(true);
    // An event during the follow-up also needs a subsequent authoritative read.
    void queue.request(true);
    reads[1].gate.resolve();
    await Promise.resolve(); await Promise.resolve();
    expect(reads).toHaveLength(3);
    reads[2].gate.resolve();
    await initial;
    expect(peak).toBe(1);
  });

  it('cancels the old read and services a new account after invalidation', async () => {
    const signals: AbortSignal[] = [];
    const queue = new RefreshQueue(async (_force, signal) => {
      signals.push(signal);
      if (signals.length === 1) await new Promise<void>(resolve => signal.addEventListener('abort', () => resolve(), { once: true }));
    });
    const pending = queue.request();
    void queue.request(true);
    queue.invalidate();
    expect(signals[0].aborted).toBe(true);
    await queue.request(true);
    await pending;
    expect(signals).toHaveLength(2);
    expect(signals[1].aborted).toBe(false);
  });

  it('can read again after a failure', async () => {
    let calls = 0;
    const queue = new RefreshQueue(async () => { if (++calls === 1) throw new Error('Offline'); });
    await expect(queue.request()).rejects.toThrow('Offline');
    await expect(queue.request(true)).resolves.toBeUndefined();
    expect(calls).toBe(2);
  });
});
