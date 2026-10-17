"""Password-confirmed, ownership-filtered portability and account erasure."""

from __future__ import annotations

import json
import secrets
import tempfile
import threading

from fastapi import Header
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from web_support import COOKIE
from starlette.background import BackgroundTask

from .database import changed
from .constants import SWIFT_EPOCH
from .encryption import key_dto, key_for
from .moderation import protect_last_admin
from .serialization import connection_dto, journal_dto, message_dto, profile_dto
from .validation import fail


class PasswordConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    password: str = Field(min_length=10, max_length=128)


class DeletionConfirmation(PasswordConfirmation):
    confirmation: str = Field(pattern=r"^DELETE$", max_length=6)


def same_account(services, db, authorization, expected_user, confirmed):
    current = services.account_user(db, authorization, expected_user)
    if (
        current["id"] != confirmed["id"]
        or current["password_hash"] != confirmed["password_hash"]
    ):
        fail("Your account changed. Sign in and try again.", 409)
    return current


def write_export(file, db, user, now):
    """Stream indexed rows into a spooled file, never include raw auth/DB rows."""
    uid = user["id"]
    profile = {
        **profile_dto(user, now),
        "username": user["username"],
        "birthDate": user["birth_date"],
        "createdAt": user["created"] - SWIFT_EPOCH,
        "role": user["role"],
    }
    key = key_for(db, uid)
    head = dict(
        format="dearly-export-v1",
        exportedAt=now - SWIFT_EPOCH,
        dateEncoding="seconds since 2001-01-01T00:00:00Z",
        profile=profile,
        encryption=key_dto(key, True) if key else None,
    )
    file.write(json.dumps(head, ensure_ascii=False).encode()[:-1])
    sources = [
        (
            "journals",
            "SELECT * FROM journals WHERE author_id=? ORDER BY created,id",
            (uid,),
            lambda row: journal_dto(db, row, uid, now),
        ),
        (
            "messages",
            "SELECT * FROM messages WHERE sender_id=? ORDER BY created,id",
            (uid,),
            message_dto,
        ),
        (
            "comments",
            "SELECT id,journal_id AS journalID,text,created-978307200 AS date FROM comments WHERE author_id=? ORDER BY created,id",
            (uid,),
            dict,
        ),
        (
            "connections",
            "SELECT * FROM connections WHERE first_id=? OR second_id=? ORDER BY started,id",
            (uid, uid),
            lambda row: connection_dto(db, row, now),
        ),
        (
            "checkIns",
            "SELECT connection_id AS connectionID,day FROM checkins WHERE user_id=? ORDER BY day",
            (uid,),
            dict,
        ),
        (
            "invitations",
            "SELECT id,sender_id AS senderID,recipient_id AS recipientID,created-978307200 AS date FROM invitations WHERE sender_id=? OR recipient_id=?",
            (uid, uid),
            dict,
        ),
        (
            "blocks",
            "SELECT blocked_id AS userID FROM blocks WHERE blocker_id=?",
            (uid,),
            dict,
        ),
        (
            "hiddenPosts",
            "SELECT journal_id AS journalID FROM hidden_posts WHERE user_id=?",
            (uid,),
            dict,
        ),
        (
            "listening",
            "SELECT journal_id AS journalID FROM listening WHERE user_id=?",
            (uid,),
            dict,
        ),
        # Never export reported_id: it can reveal an anonymous story's real author.
        (
            "reports",
            "SELECT id,journal_id AS journalID,reason,created-978307200 AS date,status FROM reports WHERE reporter_id=?",
            (uid,),
            dict,
        ),
    ]
    for name, query, parameters, convert in sources:
        file.write((' ,"' + name + '":[').encode())
        first = True
        for row in db.execute(query, parameters):
            if not first:
                file.write(b",")
            first = False
            file.write(
                json.dumps(
                    convert(row), ensure_ascii=False, separators=(",", ":")
                ).encode()
            )
        file.write(b"]")
    file.write(b"}")
    file.seek(0)


def erase_account(db, user, now):
    """Remove authored content and identifiers; retain only relationship tombstones."""
    uid = user["id"]
    protect_last_admin(db, user)
    db.execute(
        """UPDATE audit_log SET detail='{}' WHERE actor_id=? OR target_id=?
                  OR target_id IN (SELECT id FROM reports WHERE reporter_id=? OR reported_id=? OR reviewer_id=?)
                  OR target_id IN (SELECT id FROM journals WHERE author_id=?)""",
        (uid, uid, uid, uid, uid, uid),
    )
    # Older databases did not have cascading comment deletion.
    db.execute(
        "DELETE FROM comments WHERE author_id=? OR journal_id IN (SELECT id FROM journals WHERE author_id=?)",
        (uid, uid),
    )
    db.execute(
        "DELETE FROM listening WHERE user_id=? OR journal_id IN (SELECT id FROM journals WHERE author_id=?)",
        (uid, uid),
    )
    db.execute(
        "DELETE FROM hidden_posts WHERE user_id=? OR journal_id IN (SELECT id FROM journals WHERE author_id=?)",
        (uid, uid),
    )
    db.execute(
        "DELETE FROM moderation_holds WHERE journal_id IN (SELECT id FROM journals WHERE author_id=?)",
        (uid,),
    )
    db.execute(
        "DELETE FROM invitations WHERE sender_id=? OR recipient_id=?", (uid, uid)
    )
    # Erase report copies of this person's published text and free-form identifiers.
    db.execute(
        "UPDATE reports SET evidence='',reason='Account deleted',review_note='' WHERE reported_id=? OR reviewer_id=?",
        (uid, uid),
    )
    db.execute("DELETE FROM reports WHERE reporter_id=?", (uid,))
    db.execute("DELETE FROM journals WHERE author_id=?", (uid,))
    for table, field in (
        ("sessions", "user_id"),
        ("requests", "user_id"),
        ("encryption_keys", "user_id"),
        ("messages", "sender_id"),
        ("checkins", "user_id"),
    ):
        db.execute(f"DELETE FROM {table} WHERE {field}=?", (uid,))
    db.execute("DELETE FROM blocks WHERE blocker_id=? OR blocked_id=?", (uid, uid))
    db.execute(
        "UPDATE connections SET ended=? WHERE ended IS NULL AND (first_id=? OR second_id=?)",
        (now, uid, uid),
    )
    # Audit event IDs/actions remain for operator accountability; arbitrary notes do not.
    db.execute(
        """UPDATE users SET username=?,password_hash=?,nickname='Deleted account',birth_date='1900-01-01',
                  age_verified=0,symbol='leaf.fill',bio='',interests='[]',support='listen',pace='',
                  suspended=1,role='user',created=0,deleted_at=? WHERE id=?""",
        (
            "deleted-" + secrets.token_hex(24),
            "deleted$" + secrets.token_hex(32),
            now,
            uid,
        ),
    )
    changed(db)


def register_routes(app, services):
    @app.post("/v1/account/export")
    def export(
        data: PasswordConfirmation,
        authorization: str | None = Header(default=None),
        x_dearly_user: str | None = Header(default=None),
    ):
        confirmed = services.confirm_password(
            authorization, x_dearly_user, data.password
        )
        if not services.exports.acquire(blocking=False):
            fail("Data downloads are busy. Please try again shortly.", 429)
        file = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
        try:
            with services.database.connect() as db:
                user = same_account(
                    services, db, authorization, x_dearly_user, confirmed
                )
                write_export(file, db, user, services.clock())
        except BaseException:
            file.close()
            services.exports.release()
            raise

        cleanup_lock = threading.Lock()
        cleaned = False

        def cleanup():
            nonlocal cleaned
            with cleanup_lock:
                if not cleaned:
                    cleaned = True
                    file.close()
                    services.exports.release()

        def chunks():
            try:
                while data := file.read(64 * 1024):
                    yield data
            finally:
                cleanup()

        return StreamingResponse(
            chunks(),
            background=BackgroundTask(cleanup),
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="dearly-data.json"',
                "Cache-Control": "no-store",
            },
        )

    @app.post("/v1/account/delete")
    def delete(
        data: DeletionConfirmation,
        authorization: str | None = Header(default=None),
        x_dearly_user: str | None = Header(default=None),
    ):
        confirmed = services.confirm_password(
            authorization, x_dearly_user, data.password
        )
        with services.database.connect(write=True) as db:
            user = same_account(services, db, authorization, x_dearly_user, confirmed)
            erase_account(db, user, services.clock())
        services.hub.publish()
        response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
        response.delete_cookie(COOKIE, path="/")
        return response
