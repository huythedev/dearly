"""Bounded request uploads and per-process rate limiting."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict

import anyio
from fastapi import Request
from localization import error_response

from .validation import fail


class Limiter:
    """Bounded per-process token buckets. Deploy the documented single worker."""

    def __init__(self):
        self.items = OrderedDict()
        self.lock = threading.Lock()

    def check(self, key, capacity, rate):
        now = time.monotonic()
        with self.lock:
            tokens, last = self.items.pop(key, (float(capacity), now))
            tokens = min(capacity, tokens + (now - last) * rate)
            if tokens < 1:
                self.items[key] = (tokens, now)
                fail("Too many requests. Please try again in a moment.", 429)
            self.items[key] = (tokens - 1, now)
            while len(self.items) > 4096:
                self.items.popitem(last=False)


class BodyLimit:
    """Bound bytes, upload time, and concurrent readers before parsing/authentication."""

    def __init__(
        self, app, idle_timeout=5.0, total_timeout=15.0, max_uploads=32, per_ip=8
    ):
        self.app = app
        self.idle_timeout = idle_timeout
        self.total_timeout = total_timeout
        self.max_uploads = max_uploads
        self.per_ip = per_ip
        self.uploads = 0
        self.clients = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        language = Request(scope).headers.get("accept-language", "")
        has_body = any(
            k.lower() == b"transfer-encoding"
            or (k.lower() == b"content-length" and v.strip() != b"0")
            for k, v in scope["headers"]
        )
        client = (scope.get("client") or ("unknown", 0))[0]
        if has_body:
            # One event loop owns this middleware; no await occurs before admission.
            if (
                self.clients.get(client, 0) >= self.per_ip
                or self.uploads >= self.max_uploads
            ):
                return await error_response(
                    "Too many uploads in progress.",
                    429,
                    language=language,
                    headers={"Connection": "close", "Retry-After": "1"},
                )(scope, receive, send)
            self.uploads += 1
            self.clients[client] = self.clients.get(client, 0) + 1
        total = 0
        chunks = []
        try:
            with anyio.fail_after(self.total_timeout):
                while True:
                    with anyio.fail_after(self.idle_timeout):
                        message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body = message.get("body", b"")
                    total += len(body)
                    if total > 131072:
                        return await error_response(
                            "Request is too large.",
                            413,
                            language=language,
                            headers={"Connection": "close"},
                        )(scope, receive, send)
                    if body:
                        chunks.append(body)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            return await error_response(
                "Request upload timed out.",
                408,
                language=language,
                headers={"Connection": "close"},
            )(scope, receive, send)
        finally:
            if has_body:
                self.uploads -= 1
                remaining = self.clients[client] - 1
                if remaining:
                    self.clients[client] = remaining
                else:
                    del self.clients[client]
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {
                    "type": "http.request",
                    "body": b"".join(chunks),
                    "more_body": False,
                }
            return await receive()

        await self.app(scope, bounded_receive, send)
