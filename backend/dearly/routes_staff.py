"""Permission-gated staff list endpoints."""

from __future__ import annotations

import json

from fastapi import Header
from fastapi.responses import JSONResponse

from .constants import PRIVATE_HEADERS, SWIFT_EPOCH
from .moderation import require_permission
from .serialization import staff_report_dto
from .validation import fail, identifier


def register_routes(app, services):
    authenticate = services.authenticate
    database = services.database
    limiter = services.limiter

    @app.get("/v1/staff/reports")
    def staff_reports(
        status: str = "open",
        before: str | None = None,
        limit: int = 30,
        authorization: str | None = Header(default=None),
    ):
        if status not in ("open", "reviewed", "dismissed") or not 1 <= limit <= 50:
            fail("Invalid report filter.")
        with database.connect() as db:
            user = authenticate(db, authorization)
            require_permission(user, "reports.read")
            limiter.check("read:" + user["id"], 60, 1)
            where = "status=?"
            args = [status]
            if before:
                cursor = db.execute(
                    "SELECT created,id FROM reports WHERE id=?", (identifier(before),)
                ).fetchone()
                if cursor is None:
                    fail("Invalid page cursor.")
                where += " AND (created,id)<(?,?)"
                args.extend([cursor["created"], cursor["id"]])
            rows = db.execute(
                f"SELECT * FROM reports WHERE {where} ORDER BY created DESC,id DESC LIMIT ?",
                (*args, limit + 1),
            ).fetchall()
            page = rows[:limit]
            return JSONResponse(
                dict(
                    items=[staff_report_dto(db, r) for r in page],
                    nextCursor=page[-1]["id"] if len(rows) > limit else None,
                ),
                headers=PRIVATE_HEADERS,
            )

    @app.get("/v1/staff/users")
    def staff_users(
        q: str = "",
        before: str | None = None,
        limit: int = 30,
        authorization: str | None = Header(default=None),
    ):
        if not 1 <= limit <= 50 or len(q) > 80:
            fail("Invalid account filter.")
        with database.connect() as db:
            user = authenticate(db, authorization)
            require_permission(user, "users.read")
            limiter.check("read:" + user["id"], 60, 1)
            query = (
                q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                + "%"
            )
            where = "(username LIKE ? ESCAPE '\\' OR nickname LIKE ? ESCAPE '\\')"
            args = [query, query]
            if before:
                cursor = db.execute(
                    "SELECT created,id FROM users WHERE id=?", (identifier(before),)
                ).fetchone()
                if cursor is None:
                    fail("Invalid page cursor.")
                where += " AND (created,id)<(?,?)"
                args.extend([cursor["created"], cursor["id"]])
            rows = db.execute(
                f"""SELECT id,username,nickname,role,suspended,age_verified,birth_date,created
                                 FROM users WHERE {where} ORDER BY created DESC,id DESC LIMIT ?""",
                (*args, limit + 1),
            ).fetchall()
            page = rows[:limit]
            items = [
                dict(
                    id=r["id"],
                    username=r["username"],
                    nickname=r["nickname"],
                    role=r["role"],
                    suspended=bool(r["suspended"]),
                    ageVerified=bool(r["age_verified"]),
                    birthDate=r["birth_date"],
                )
                for r in page
            ]
            return JSONResponse(
                dict(
                    items=items,
                    nextCursor=page[-1]["id"] if len(rows) > limit else None,
                ),
                headers=PRIVATE_HEADERS,
            )

    @app.get("/v1/staff/audit")
    def staff_audit(
        before: int | None = None,
        limit: int = 30,
        authorization: str | None = Header(default=None),
    ):
        if not 1 <= limit <= 50 or (before is not None and before < 1):
            fail("Invalid page cursor.")
        with database.connect() as db:
            user = authenticate(db, authorization)
            require_permission(user, "audit.read")
            limiter.check("read:" + user["id"], 60, 1)
            rows = db.execute(
                """SELECT a.*,u.nickname AS actor_name FROM audit_log a LEFT JOIN users u ON u.id=a.actor_id
                                 WHERE (? IS NULL OR a.id<?) ORDER BY a.id DESC LIMIT ?""",
                (before, before, limit + 1),
            ).fetchall()
            page = rows[:limit]
            items = [
                dict(
                    id=r["id"],
                    actorID=r["actor_id"],
                    actorName=r["actor_name"] or "Server CLI",
                    action=r["action"],
                    targetID=r["target_id"],
                    detail=json.loads(r["detail"]),
                    date=r["created"] - SWIFT_EPOCH,
                )
                for r in page
            ]
            return JSONResponse(
                dict(
                    items=items,
                    nextCursor=page[-1]["id"] if len(rows) > limit else None,
                ),
                headers=PRIVATE_HEADERS,
            )
