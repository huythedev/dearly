"""Personal state, pagination, and the REST action endpoint."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import Header
from fastapi.responses import JSONResponse, Response

from .constants import PRIVATE_HEADERS, SWIFT_EPOCH
from .policies import active
from .serialization import (
    connection_dto,
    journal_dto,
    message_dto,
    profile_dto,
    snapshot,
)
from .validation import Action, fail, identifier


def register_routes(app, services):
    authenticate = services.authenticate
    clock = services.clock
    database = services.database
    execute_action = services.execute_action
    limiter = services.limiter

    @app.get("/v1/state")
    def state(
        authorization: str | None = Header(default=None),
        if_none_match: str | None = Header(default=None),
    ):
        with database.connect() as db:
            user = authenticate(db, authorization)
            now = clock()
            limiter.check("read:" + user["id"], 60, 1)
            revision = db.execute("SELECT revision FROM meta WHERE id=1").fetchone()[0]
            day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
            tag = (
                '"'
                + hashlib.sha256(f"{user['id']}:{revision}:{day}".encode()).hexdigest()
                + '"'
            )
            headers = {
                "ETag": tag,
                "Cache-Control": "no-store",
                "Vary": "Authorization",
            }
            if if_none_match == tag:
                return Response(status_code=304, headers=headers)
            return JSONResponse(
                dict(state=snapshot(db, user, now), serverNow=now - SWIFT_EPOCH),
                headers=headers,
            )

    @app.post("/v1/actions")
    def action(
        data: Action,
        authorization: str | None = Header(default=None),
        x_dearly_user: str | None = Header(default=None),
    ):
        return execute_action(data, authorization, x_dearly_user)

    @app.get("/v1/journals")
    def own_journals(
        before: str | None = None,
        limit: int = 40,
        authorization: str | None = Header(default=None),
    ):
        if not 1 <= limit <= 60:
            fail("The limit must be between 1 and 60.")
        with database.connect() as db:
            user = authenticate(db, authorization)
            uid = user["id"]
            now = clock()
            limiter.check("read:" + uid, 60, 1)
            args = [uid]
            where = "author_id=?"
            if before:
                cursor = db.execute(
                    "SELECT created,id FROM journals WHERE id=? AND author_id=?",
                    (identifier(before), uid),
                ).fetchone()
                if cursor is None:
                    fail("Invalid page cursor.")
                where += " AND (created,id)<(?,?)"
                args.extend([cursor["created"], cursor["id"]])
            rows = db.execute(
                f"SELECT * FROM journals WHERE {where} ORDER BY created DESC,id DESC LIMIT ?",
                (*args, limit + 1),
            ).fetchall()
            page = rows[:limit]
            return JSONResponse(
                dict(
                    items=[journal_dto(db, r, uid, now) for r in page],
                    nextCursor=page[-1]["id"] if len(rows) > limit else None,
                ),
                headers=PRIVATE_HEADERS,
            )

    @app.get("/v1/connections")
    def archived_connections(
        before: str | None = None,
        limit: int = 20,
        authorization: str | None = Header(default=None),
    ):
        if not 1 <= limit <= 50:
            fail("limit must be between 1 and 50.")
        with database.connect() as db:
            user = authenticate(db, authorization)
            uid = user["id"]
            now = clock()
            limiter.check("read:" + uid, 60, 1)
            where = "ended IS NOT NULL AND (first_id=? OR second_id=?)"
            args = [uid, uid]
            if before:
                cursor = db.execute(
                    """SELECT started,id FROM connections WHERE id=? AND ended IS NOT NULL
                                     AND (first_id=? OR second_id=?)""",
                    (identifier(before), uid, uid),
                ).fetchone()
                if cursor is None:
                    fail("Invalid page cursor.")
                where += " AND (started,id)<(?,?)"
                args.extend([cursor["started"], cursor["id"]])
            rows = db.execute(
                f"SELECT * FROM connections WHERE {where} ORDER BY started DESC,id DESC LIMIT ?",
                (*args, limit + 1),
            ).fetchall()
            page = rows[:limit]
            profile_ids = {uid}
            for row in page:
                profile_ids.update((row["first_id"], row["second_id"]))
            marks = ",".join("?" for _ in profile_ids)
            profiles = [
                profile_dto(r, now)
                for r in db.execute(
                    f"SELECT * FROM users WHERE id IN ({marks})", list(profile_ids)
                )
            ]
            return JSONResponse(
                dict(
                    items=[connection_dto(db, r, now) for r in page],
                    profiles=profiles,
                    nextCursor=page[-1]["id"] if len(rows) > limit else None,
                ),
                headers=PRIVATE_HEADERS,
            )

    @app.get("/v1/messages")
    def history(
        connectionID: str,
        before: str | None = None,
        limit: int = 50,
        authorization: str | None = Header(default=None),
    ):
        if not 1 <= limit <= 100:
            fail("The limit must be between 1 and 100.")
        with database.connect() as db:
            user = authenticate(db, authorization)
            conn = active(db, user["id"])
            if conn is None or conn["id"] != identifier(connectionID):
                fail("You do not have permission to read this chat.", 403)
            limiter.check("read:" + user["id"], 60, 1)
            args = [conn["id"]]
            where = "connection_id=?"
            if before:
                cursor = db.execute(
                    "SELECT created,id FROM messages WHERE id=? AND connection_id=?",
                    (identifier(before), conn["id"]),
                ).fetchone()
                if cursor is None:
                    fail("Invalid page cursor.")
                where += " AND (created,id)<(?,?)"
                args.extend([cursor["created"], cursor["id"]])
            rows = db.execute(
                f"SELECT * FROM messages WHERE {where} ORDER BY created DESC,id DESC LIMIT ?",
                (*args, limit + 1),
            ).fetchall()
            page = rows[:limit]
            return JSONResponse(
                dict(
                    items=[message_dto(r) for r in reversed(page)],
                    nextCursor=page[-1]["id"] if len(rows) > limit else None,
                ),
                headers=PRIVATE_HEADERS,
            )
