/** Serialize snapshots and keep an invalidation that arrives during a read. */
export class RefreshQueue {
  private running: Promise<void> | null = null;
  private controller: AbortController | null = null;
  private pending = false;
  private force = false;

  constructor(private read: (force: boolean, signal: AbortSignal) => Promise<void>) {}

  request(force = false): Promise<void> {
    if (this.running) {
      if (force) { this.pending = true; this.force = true; }
      return this.running;
    }
    this.force = force;
    this.running = this.drain().finally(() => { this.running = null; });
    return this.running;
  }

  invalidate() {
    this.pending = false;
    this.force = false;
    this.controller?.abort();
  }

  private async drain() {
    do {
      const force = this.force;
      this.pending = false;
      this.force = false;
      const controller = this.controller = new AbortController();
      try { await this.read(force, controller.signal); }
      finally { if (this.controller === controller) this.controller = null; }
    } while (this.pending);
  }
}
