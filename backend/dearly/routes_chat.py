"""Authenticated WebSocket chat lifecycle and event delivery."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import suppress

import anyio
from fastapi import WebSocket, WebSocketDisconnect
from localization import RequestError
from pydantic import ValidationError
from web_support import COOKIE, same_origin

from .validation import Action, fail


async def close_socket(websocket: WebSocket, code: int) -> None:
    # The browser can leave while an expiry, validation or quota check is running.
    with suppress(WebSocketDisconnect, OSError):
        await websocket.close(code=code)


def register_routes(app, services):
    execute_action = services.execute_action
    hub = services.hub
    limiter = services.limiter
    socket_user = services.socket_user

    @app.websocket("/ws/chat")
    async def chat(websocket: WebSocket):
        # Browser cookies are never accepted across origins; native clients authenticate in-frame.
        if not same_origin(websocket) or (
            websocket.cookies.get(COOKIE) and not websocket.headers.get("origin")
        ):
            await close_socket(websocket, 4403)
            return
        try:
            ip = websocket.client.host if websocket.client else "unknown"
            limiter.check("socket-ip:" + ip, 12, 1 / 10)
        except RequestError:
            await close_socket(websocket, 4429)
            return
        tasks = []
        try:
            await websocket.accept()
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=5)
            if len(raw.encode()) > 16384:
                await close_socket(websocket, 1009)
                return
            frame = json.loads(raw)
            if not isinstance(frame, dict) or frame.get("type") != "authenticate":
                await close_socket(websocket, 4401)
                return
            token = websocket.cookies.get(COOKIE) or frame.get("token")
            if not isinstance(token, str) or len(token) > 128:
                await close_socket(websocket, 4401)
                return
            authorization = "Bearer " + token
            uid, _ = await anyio.to_thread.run_sync(socket_user, authorization)
            with hub.subscribe(uid) as queue:
                await websocket.send_json({"type": "ready", "userID": uid})
                incoming = asyncio.create_task(websocket.receive_text())
                outgoing = asyncio.create_task(queue.get())
                tasks = [incoming, outgoing]
                while True:
                    done, _ = await asyncio.wait(
                        tasks, timeout=15, return_when=asyncio.FIRST_COMPLETED
                    )
                    # Re-check revocation and suspension even on an idle socket / CLI changes.
                    await anyio.to_thread.run_sync(socket_user, authorization)
                    if not done:
                        await websocket.send_json({"type": "ping"})
                        continue
                    if incoming in done:
                        raw = incoming.result()
                        if len(raw.encode()) > 16384:
                            await close_socket(websocket, 1009)
                            return
                        frame = json.loads(raw)
                        request_id = (
                            frame.get("requestID") if isinstance(frame, dict) else None
                        )
                        try:
                            limiter.check("socket-frame:" + uid, 60, 2)
                            if not isinstance(frame, dict):
                                fail("Invalid chat frame.")
                            if frame.get("type") == "ping":
                                await websocket.send_json({"type": "pong"})
                            elif frame.get("type") == "message.send":
                                command = Action.model_validate(
                                    {
                                        "requestID": request_id,
                                        "kind": "message.send",
                                        "payload": {
                                            "connectionID": frame.get("connectionID"),
                                            "text": frame.get("text"),
                                        },
                                    }
                                )
                                result = await anyio.to_thread.run_sync(
                                    execute_action, command, authorization
                                )
                                await websocket.send_json(
                                    {
                                        "type": "ack",
                                        "requestID": request_id,
                                        "result": result,
                                    }
                                )
                            else:
                                fail("This chat frame is not supported.")
                        except (RequestError, ValidationError) as exc:
                            status = (
                                exc.status_code
                                if isinstance(exc, RequestError)
                                else 400
                            )
                            detail = (
                                str(exc.detail)
                                if isinstance(exc, RequestError)
                                else "Invalid chat message."
                            )
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "requestID": request_id,
                                    "status": status,
                                    "detail": detail,
                                }
                            )
                            if status == 429:
                                await close_socket(websocket, 4429)
                                return
                        incoming = asyncio.create_task(websocket.receive_text())
                        tasks = [incoming, outgoing]
                    if outgoing in done:
                        event = outgoing.result()
                        _, message = await anyio.to_thread.run_sync(
                            socket_user, authorization, event
                        )
                        if message:
                            await websocket.send_json(
                                {"type": "message", "message": message}
                            )
                        elif event["type"] == "state.changed":
                            await websocket.send_json(event)
                        outgoing = asyncio.create_task(queue.get())
                    tasks = [incoming, outgoing]
        except RequestError as exc:
            await close_socket(websocket, 4401 if exc.status_code == 401 else 4403)
        except OverflowError:
            await close_socket(websocket, 4429)
        except (
            asyncio.TimeoutError,
            json.JSONDecodeError,
            UnicodeError,
            KeyError,
            TypeError,
        ):
            await close_socket(websocket, 1008)
        except sqlite3.OperationalError:
            await close_socket(websocket, 1013)
        except WebSocketDisconnect:
            pass
        except asyncio.CancelledError:
            pass
        finally:
            for task in tasks:
                task.cancel()
            with anyio.CancelScope(shield=True):
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
