"""Authentication, sessions, and shared mutation execution."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading

from realtime import ChatHub

from .actions import apply_action
from .constants import ROLE_PERMISSIONS, SESSION_LIFETIME, STAFF_ACTIONS, SWIFT_EPOCH
from .database import changed
from .limits import Limiter
from .moderation import require_permission
from .policies import active, eligible
from .serialization import message_dto
from .validation import Action, fail, identifier


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"pbkdf2-sha256$600000${salt.hex()}${digest.hex()}"


def password_matches(password: str, encoded: str) -> bool:
    if not encoded.startswith("pbkdf2-sha256$"):
        return False
    _, rounds, salt, expected = encoded.split("$")
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), int(rounds)
    )
    return hmac.compare_digest(digest.hex(), expected)


class AppServices:
    """Per-application state shared by HTTP and WebSocket routes."""

    def __init__(self, database, clock):
        self.database = database
        self.clock = clock
        self.limiter = Limiter()
        self.hashing = threading.BoundedSemaphore(2)
        self.exports = threading.BoundedSemaphore(2)
        self.hub = ChatHub()

    def authenticate(self, db, authorization):
        if (
            not authorization
            or not authorization.startswith("Bearer ")
            or len(authorization) > 512
        ):
            fail("Please log in.", 401)
        digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
        user = db.execute(
            "SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires>? AND u.suspended=0 AND u.deleted_at IS NULL",
            (digest, self.clock()),
        ).fetchone()
        if user is None:
            fail(
                "Your session has expired or your account is locked. Please log in again.",
                401,
            )
        return user

    def auth_rate(self, request, username):
        ip = request.client.host if request.client else "unknown"
        self.limiter.check("auth-ip:" + ip, 12, 1 / 10)
        self.limiter.check("auth-user:" + username.lower(), 8, 1 / 15)

    def account_user(self, db, authorization, expected_user=None):
        user = self.authenticate(db, authorization)
        if expected_user is not None and expected_user != user["id"]:
            fail("Your account changed. Reload the page before trying again.", 409)
        return user

    def confirm_password(self, authorization, expected_user, password):
        with self.database.connect() as db:
            user = self.account_user(db, authorization, expected_user)
        self.limiter.check("privacy:" + user["id"], 5, 1 / 60)
        if not self.hashing.acquire(blocking=False):
            fail("Sign-in is busy. Please try again shortly.", 429)
        try:
            valid = password_matches(password, user["password_hash"])
        finally:
            self.hashing.release()
        if not valid:
            fail("Incorrect password.", 403)
        return user

    def staff_user(self, db, authorization, permission, expected_user=None):
        user = self.authenticate(db, authorization)
        require_permission(user, permission)
        if expected_user is not None and expected_user != user["id"]:
            fail("Your account changed. Reload the page before trying again.", 409)
        return user

    def staff_access(self, authorization, expected_user=None):
        with self.database.connect() as db:
            user = self.staff_user(db, authorization, "reports.read", expected_user)
            self.limiter.check("read:" + user["id"], 60, 1)
            return dict(
                userID=user["id"],
                currentUserRole=user["role"],
                permissions=sorted(ROLE_PERMISSIONS[user["role"]]),
            )

    def session(self, db, uid):
        token = secrets.token_urlsafe(32)
        expires = self.clock() + SESSION_LIFETIME
        db.execute("DELETE FROM sessions WHERE expires<?", (self.clock(),))
        db.execute(
            "DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM sessions WHERE user_id=? ORDER BY expires DESC LIMIT -1 OFFSET 7)",
            (uid,),
        )
        db.execute(
            "INSERT INTO sessions VALUES(?,?,?)",
            (hashlib.sha256(token.encode()).hexdigest(), uid, expires),
        )
        return dict(token=token, userID=uid, expiresAt=expires - SWIFT_EPOCH)

    def execute_action(self, data: Action, authorization, expected_user=None):
        """Commit an authorized, idempotent mutation before publishing its event."""
        rid = identifier(data.requestID)
        fingerprint = hashlib.sha256(
            json.dumps(
                {"kind": data.kind, "payload": data.payload},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        with self.database.connect(write=True) as db:
            user = self.authenticate(db, authorization)
            uid = user["id"]
            if expected_user is not None and expected_user != uid:
                fail("Your account changed. Reload the page before trying again.", 409)
            now = self.clock()
            self.limiter.check("write:" + uid, 40, 1)
            if data.kind.startswith("staff."):
                require_permission(user, STAFF_ACTIONS.get(data.kind, "unknown"))
            previous = db.execute(
                "SELECT * FROM requests WHERE user_id=? AND request_id=?", (uid, rid)
            ).fetchone()
            if previous:
                if previous["payload_hash"] != fingerprint:
                    fail("This request ID was already used for different content.", 409)
                return json.loads(previous["result"])
            result = {
                "ok": True,
                **apply_action(db, user, data.kind, data.payload, now),
            }
            db.execute(
                "INSERT INTO requests VALUES(?,?,?,?,?)",
                (uid, rid, fingerprint, json.dumps(result), now),
            )
            db.execute("DELETE FROM requests WHERE created<?", (now - 7 * 86400,))
            changed(db)
        if data.kind == "message.send":
            self.hub.publish(
                {
                    "type": "message",
                    "id": result["id"],
                    "connectionID": identifier(data.payload["connectionID"]),
                }
            )
        else:
            self.hub.publish()
        return result

    def socket_user(self, authorization, event=None):
        with self.database.connect() as db:
            user = self.authenticate(db, authorization)
            message = None
            if event and event["type"] == "message":
                conn = active(db, user["id"])
                if (
                    conn
                    and conn["id"] == event["connectionID"]
                    and eligible(db, conn["first_id"], conn["second_id"], self.clock())
                ):
                    row = db.execute(
                        "SELECT * FROM messages WHERE id=? AND connection_id=?",
                        (event["id"], conn["id"]),
                    ).fetchone()
                    if row:
                        message = message_dto(row)
            return (user["id"], message)
