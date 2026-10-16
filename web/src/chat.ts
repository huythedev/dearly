import { APIError } from './api';
import type { Command, Message } from './types';

export type ChatStatus = 'connecting' | 'connected' | 'reconnecting';
type Pending = { resolve: (value: { ok: boolean; id?: string }) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> };

export class ChatTransport {
  private socket: WebSocket | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private pending = new Map<string, Pending>();
  private stopped = false;
  private ready = false;
  private attempts = 0;
  constructor(private callbacks: {
    status: (value: ChatStatus) => void; message: (value: Message) => void;
    changed: () => void; expired: () => void;
  }) { this.connect(); }

  private connect() {
    if (this.stopped) return;
    this.callbacks.status(this.attempts ? 'reconnecting' : 'connecting');
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = this.socket = new WebSocket(`${protocol}//${location.host}/ws/chat`);
    const current = () => !this.stopped && this.socket === socket;
    socket.onopen = () => { if (current()) socket.send(JSON.stringify({ type: 'authenticate' })); };
    socket.onmessage = event => {
      if (!current()) return;
      let frame;
      try { frame = JSON.parse(event.data); } catch { return; }
      if (!frame || typeof frame !== 'object') return;
      if (frame.type === 'ready') {
        this.ready = true; this.attempts = 0;
        this.callbacks.status('connected'); this.callbacks.changed();
      } else if (frame.type === 'message') this.callbacks.message(frame.message);
      else if (frame.type === 'state.changed') this.callbacks.changed();
      else if (frame.type === 'ping') socket.send(JSON.stringify({ type: 'ping' }));
      else if (frame.type === 'ack' || frame.type === 'error') {
        const pending = this.pending.get(frame.requestID);
        if (!pending) return;
        clearTimeout(pending.timer); this.pending.delete(frame.requestID);
        if (frame.type === 'ack') pending.resolve(frame.result);
        else pending.reject(new APIError(frame.status, frame.detail));
      }
    };
    socket.onclose = event => {
      if (!current()) return;
      this.ready = false;
      this.failPending();
      if (event.code === 4401) { this.callbacks.expired(); return; }
      this.callbacks.status('reconnecting');
      const delay = Math.min(30000, 1000 * 2 ** Math.min(this.attempts++, 5));
      this.timer = setTimeout(() => this.connect(), delay + Math.random() * 400);
    };
    socket.onerror = () => { if (current()) socket.close(); };
  }

  send(value: Command): Promise<{ ok: boolean; id?: string }> {
    if (!this.ready || this.socket?.readyState !== WebSocket.OPEN) return Promise.reject(new Error('Chat reconnecting.'));
    if (this.pending.has(value.requestID)) return Promise.reject(new Error('Chat request already pending.'));
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(value.requestID); reject(new Error('Chat reply timed out.')); }, 10000);
      this.pending.set(value.requestID, { resolve, reject, timer });
      try { this.socket!.send(JSON.stringify({ type: 'message.send', requestID: value.requestID, ...value.payload })); }
      catch (error) {
        clearTimeout(timer); this.pending.delete(value.requestID);
        reject(error);
      }
    });
  }

  private failPending() {
    for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.reject(new Error('Chat disconnected.')); }
    this.pending.clear();
  }

  close() {
    this.stopped = true; this.ready = false;
    if (this.timer) clearTimeout(this.timer);
    this.failPending(); this.socket?.close();
  }
}
