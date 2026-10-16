"""Bounded, single-worker event hub; publishers may run in FastAPI's thread pool."""
import asyncio
import threading
from contextlib import contextmanager


class ChatHub:
    def __init__(self):
        self.lock = threading.Lock()
        self.peers = {}

    @contextmanager
    def subscribe(self, user_id):
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue(maxsize=32)
        key = object()
        with self.lock:
            if len(self.peers) >= 32 or sum(p[0] == user_id for p in self.peers.values()) >= 4:
                raise OverflowError('Too many open chat connections.')
            self.peers[key] = (user_id, loop, queue)
        try:
            yield queue
        finally:
            with self.lock:
                self.peers.pop(key, None)

    @staticmethod
    def offer(queue, event):
        if queue.full():
            while not queue.empty():
                queue.get_nowait()
            queue.put_nowait({'type': 'state.changed'})
        else:
            queue.put_nowait(event)

    def publish(self, event=None):
        event = event or {'type': 'state.changed'}
        with self.lock:
            peers = list(self.peers.values())
        for _, loop, queue in peers:
            if not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(self.offer, queue, event)
                except RuntimeError:
                    pass  # A disconnect may close its event loop after the check.
