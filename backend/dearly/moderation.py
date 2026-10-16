"""Staff permissions, audit records, and moderation mutations."""

from __future__ import annotations

import json

from .constants import ROLE_PERMISSIONS, STAFF_ACTIONS
from .validation import bool_field, fail, identifier, text_field, validate_birth


def require_permission(user, permission):
    if permission not in ROLE_PERMISSIONS.get(user["role"], ()):
        fail("You do not have permission to perform this action.", 403)


def audit(db, actor, action, target, detail, now):
    db.execute(
        "INSERT INTO audit_log(actor_id,action,target_id,detail,created) VALUES(?,?,?,?,?)",
        (actor, action, target, json.dumps(detail, ensure_ascii=False), now),
    )


def protect_last_admin(db, user):
    if user["role"] == "admin" and not user["suspended"]:
        count = db.execute(
            "SELECT count(*) FROM users WHERE role='admin' AND suspended=0"
        ).fetchone()[0]
        if count <= 1:
            fail("The last active admin cannot be removed or suspended.", 409)


def set_role(db, user, role, actor, reason, now):
    if role not in ROLE_PERMISSIONS:
        fail("Invalid role.")
    if user["role"] == role:
        return
    if role != "admin":
        protect_last_admin(db, user)
    db.execute("UPDATE users SET role=? WHERE id=?", (role, user["id"]))
    audit(
        db,
        actor,
        "user.role",
        user["id"],
        {"from": user["role"], "to": role, "reason": reason},
        now,
    )


def set_suspended(db, user, suspended, actor, reason, now):
    if bool(user["suspended"]) == suspended:
        return
    uid = user["id"]
    if suspended:
        protect_last_admin(db, user)
    db.execute("UPDATE users SET suspended=? WHERE id=?", (int(suspended), uid))
    if suspended:
        db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        db.execute(
            "DELETE FROM invitations WHERE sender_id=? OR recipient_id=?", (uid, uid)
        )
        db.execute(
            "UPDATE connections SET ended=? WHERE ended IS NULL AND (first_id=? OR second_id=?)",
            (now, uid, uid),
        )
    audit(
        db,
        actor,
        "user.suspend" if suspended else "user.restore",
        uid,
        {"reason": reason},
        now,
    )


def verify_age(db, user, birth, actor, reason, now):
    birth = validate_birth(birth, now)
    uid = user["id"]
    db.execute("UPDATE users SET birth_date=?,age_verified=1 WHERE id=?", (birth, uid))
    if user["birth_date"] != birth:
        db.execute(
            "UPDATE connections SET ended=? WHERE ended IS NULL AND (first_id=? OR second_id=?)",
            (now, uid, uid),
        )
        db.execute(
            "DELETE FROM invitations WHERE sender_id=? OR recipient_id=?", (uid, uid)
        )
    # Birth dates and credentials never enter the audit detail.
    audit(
        db,
        actor,
        "user.verify_age",
        uid,
        {"birthDateCorrected": user["birth_date"] != birth, "reason": reason},
        now,
    )


def review_report(db, rid, status, note, actor, now):
    if status not in ("open", "reviewed", "dismissed"):
        fail("Invalid report status.")
    if not db.execute("SELECT 1 FROM reports WHERE id=?", (rid,)).fetchone():
        fail("Report not found.", 404)
    db.execute(
        "UPDATE reports SET status=?,review_note=?,reviewer_id=?,reviewed_at=? WHERE id=?",
        (status, note, actor, now, rid),
    )
    audit(db, actor, "report.review", rid, {"status": status, "note": note}, now)


def apply_staff_action(db, user, kind, p, now):
    permission = STAFF_ACTIONS.get(kind)
    if permission is None:
        fail("Invalid staff action.")
    require_permission(user, permission)
    allowed = {
        "staff.report.review": {"id", "status", "reason"},
        "staff.report.hide": {"id", "reason"},
        "staff.report.restore": {"id", "reason"},
        "staff.user.suspend": {"userID", "suspended", "reason"},
        "staff.user.verify_age": {"userID", "birthDate", "reason"},
        "staff.user.role": {"userID", "role", "reason"},
    }[kind]
    if set(p) - allowed:
        fail("Invalid field in staff action.")
    reason = text_field(p, "reason", 1000)
    if kind == "staff.report.review":
        review_report(
            db, identifier(p.get("id")), p.get("status"), reason, user["id"], now
        )
    elif kind in ("staff.report.hide", "staff.report.restore"):
        rid = identifier(p.get("id"))
        row = db.execute(
            """SELECT j.* FROM reports r JOIN journals j ON j.id=r.journal_id
                            WHERE r.id=? AND j.author_id=r.reported_id""",
            (rid,),
        ).fetchone()
        if row is None:
            fail("The post has been deleted.", 409)
        held = db.execute(
            "SELECT 1 FROM moderation_holds WHERE journal_id=?", (row["id"],)
        ).fetchone()
        if kind == "staff.report.restore":
            if not held:
                fail("This entry has no sharing restriction.", 409)
            db.execute("DELETE FROM moderation_holds WHERE journal_id=?", (row["id"],))
            review_report(db, rid, "reviewed", reason, user["id"], now)
            audit(
                db,
                user["id"],
                "report.restore",
                rid,
                {"journalID": row["id"], "reason": reason},
                now,
            )
            return {}
        if held or row["audience"] != "community":
            fail("The community post is hidden or no longer public.", 409)
        db.execute(
            "INSERT INTO moderation_holds VALUES(?,?,?)", (row["id"], user["id"], now)
        )
        # The owner's private body survives. Only the reported public post is withdrawn.
        db.execute(
            "UPDATE journals SET audience='privateOnly',shared_text='',connection_id=NULL WHERE id=?",
            (row["id"],),
        )
        db.execute("DELETE FROM comments WHERE journal_id=?", (row["id"],))
        db.execute("DELETE FROM listening WHERE journal_id=?", (row["id"],))
        review_report(db, rid, "reviewed", reason, user["id"], now)
        audit(
            db,
            user["id"],
            "report.hide",
            rid,
            {"journalID": row["id"], "reason": reason},
            now,
        )
    else:
        target = db.execute(
            "SELECT * FROM users WHERE id=?", (identifier(p.get("userID")),)
        ).fetchone()
        if target is None:
            fail("Account not found.", 404)
        if target["id"] == user["id"] or target["role"] == "admin":
            fail("Use a backend server command to change an admin account.", 403)
        if kind == "staff.user.role":
            if p.get("role") not in ("user", "moderator"):
                fail(
                    "Admin access can only be granted with a backend server command.",
                    403,
                )
            set_role(db, target, p["role"], user["id"], reason, now)
        elif kind == "staff.user.suspend":
            if "suspended" not in p:
                fail("The suspended field is required.")
            set_suspended(
                db, target, bool_field(p, "suspended"), user["id"], reason, now
            )
        else:
            verify_age(
                db, target, text_field(p, "birthDate", 10), user["id"], reason, now
            )
    return {}
