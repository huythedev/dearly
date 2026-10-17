"""Account registration, login, logout, and health routes."""

from __future__ import annotations

import hashlib
import json

from fastapi import Header, Request
from fastapi.responses import JSONResponse
from web_support import COOKIE, browser_session

from .database import changed
from .service import password_hash, password_matches
from .validation import Credentials, Registration, fail, new_id, validate_birth


def register_routes(app, services):
    auth_rate = services.auth_rate
    authenticate = services.authenticate
    clock = services.clock
    database = services.database
    hashing = services.hashing
    hub = services.hub
    session = services.session

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.5.0", "dayBoundary": "UTC"}

    @app.post("/v1/auth/register", status_code=201)
    def register(data: Registration, request: Request):
        auth_rate(request, data.username)
        birth = validate_birth(data.birthDate, clock())
        nickname = data.nickname.strip()
        if not nickname:
            fail("Please enter a nickname.")
        if not hashing.acquire(blocking=False):
            fail("Sign-in is busy. Please try again shortly.", 429)
        try:
            encoded = password_hash(data.password)
        finally:
            hashing.release()
        with database.connect(write=True) as db:
            if db.execute(
                "SELECT 1 FROM users WHERE username=?", (data.username.lower(),)
            ).fetchone():
                fail("This username is already taken.", 409)
            uid = new_id()
            # Explicit defaults also apply to databases whose original column defaults were Vietnamese.
            db.execute(
                "INSERT INTO users(id,username,password_hash,nickname,birth_date,created,interests,support,pace) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    uid,
                    data.username.lower(),
                    encoded,
                    nickname,
                    birth,
                    clock(),
                    json.dumps(["Music", "Reading"]),
                    "listen",
                    "Evenings",
                ),
            )
            changed(db)
            return browser_session(session(db, uid), request, 201)

    @app.post("/v1/auth/login")
    def login(data: Credentials, request: Request):
        auth_rate(request, data.username)
        with database.connect() as db:
            user = db.execute(
                "SELECT * FROM users WHERE username=?", (data.username.lower(),)
            ).fetchone()
        # Fixed-cost dummy verification avoids a fast nonexistent-username path.
        dummy = "pbkdf2-sha256$600000$" + "00" * 16 + "$" + "00" * 32
        if not hashing.acquire(blocking=False):
            fail("Sign-in is busy. Please try again shortly.", 429)
        try:
            valid = password_matches(
                data.password, user["password_hash"] if user and user["deleted_at"] is None else dummy
            )
        finally:
            hashing.release()
        if not valid or user is None or user["suspended"] or user["deleted_at"] is not None:
            fail("Incorrect username or password.", 401)
        with database.connect(write=True) as db:
            if db.execute(
                "SELECT suspended FROM users WHERE id=?", (user["id"],)
            ).fetchone()[0]:
                fail("This account is unavailable.", 401)
            return browser_session(session(db, user["id"]), request)

    @app.post("/v1/auth/logout")
    def logout(authorization: str | None = Header(default=None)):
        with database.connect(write=True) as db:
            authenticate(db, authorization)
            db.execute(
                "DELETE FROM sessions WHERE token_hash=?",
                (hashlib.sha256(authorization[7:].encode()).hexdigest(),),
            )
        hub.publish()
        response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
        response.delete_cookie(COOKIE, path="/")
        return response
