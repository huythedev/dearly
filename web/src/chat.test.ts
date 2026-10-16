import { afterEach, expect, it, vi } from 'vitest';
import { ChatTransport } from './chat';
import { command } from './api';

class Socket {
  static OPEN = 1;
  static instances: Socket[] = [];
  readyState = 1;
  onopen = () => {};
  onmessage = (_event: { data: string }) => {};
  onclose = (_event: { code: number }) => {};
  onerror = () => {};
  send = vi.fn();
  close = vi.fn();
  constructor(_url: string) { Socket.instances.push(this); }
  frame(frame: unknown) { this.onmessage({ data: JSON.stringify(frame) }); }
}
function connected() {
  Socket.instances = [];
  vi.stubGlobal('WebSocket', Socket);
  vi.stubGlobal('location', { protocol: 'https:', host: 'dearly.test' });
  const callbacks = { status: vi.fn(), message: vi.fn(), changed: vi.fn(), expired: vi.fn() };
  const transport = new ChatTransport(callbacks);
  const socket = Socket.instances[0]; socket.frame({ type: 'ready' });
  return { transport, socket, callbacks };
}
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it('ignores late callbacks from a closed transport, including expiration', () => {
  vi.useFakeTimers();
  const { transport, socket, callbacks } = connected();
  transport.close();
  socket.onopen(); socket.frame({ type: 'state.changed' });
  socket.onclose({ code: 4401 }); socket.frame(null);
  expect(callbacks.changed).toHaveBeenCalledTimes(1);
  expect(callbacks.expired).not.toHaveBeenCalled();
  expect(socket.send).not.toHaveBeenCalled();
  expect(vi.getTimerCount()).toBe(0);
});

it('clears a pending acknowledgement when sending throws', async () => {
  vi.useFakeTimers();
  const { transport, socket } = connected();
  socket.send.mockImplementationOnce(() => { throw new Error('Socket closed'); });
  const value = command('message.send', { text: 'Hello' });
  await expect(transport.send(value)).rejects.toThrow('Socket closed');
  expect(vi.getTimerCount()).toBe(0);
  const retry = transport.send(value);
  socket.frame({ type: 'ack', requestID: value.requestID, result: { ok: true, id: 'saved' } });
  await expect(retry).resolves.toEqual({ ok: true, id: 'saved' });
  expect(vi.getTimerCount()).toBe(0);
  transport.close();
});
