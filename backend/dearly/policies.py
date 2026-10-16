"""Read access, connection eligibility, and membership rules."""

from __future__ import annotations

from datetime import datetime, timezone

from .validation import age_on, fail, identifier


def blocked(db, a, b):
    return (
        db.execute(
            "SELECT 1 FROM blocks WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)",
            (a, b, b, a),
        ).fetchone()
        is not None
    )


def active(db, uid):
    return db.execute(
        "SELECT * FROM connections WHERE ended IS NULL AND (first_id=? OR second_id=?)",
        (uid, uid),
    ).fetchone()


def eligible(db, a, b, now):
    if a == b or blocked(db, a, b):
        return False
    users = db.execute("SELECT * FROM users WHERE id IN (?,?)", (a, b)).fetchall()
    if len(users) != 2 or any(not u["age_verified"] or u["suspended"] for u in users):
        return False
    today = datetime.fromtimestamp(now, timezone.utc).date()
    ages = [age_on(u["birth_date"], today) for u in users]
    if min(ages) < 16:
        return False
    if min(ages) < 18:
        return max(ages) < 18 and abs(ages[0] - ages[1]) <= 1
    return True


def can_invite(db, a, b, now):
    return eligible(db, a, b, now) and active(db, a) is None and active(db, b) is None


def readable(db, journal, uid):
    if journal["author_id"] == uid:
        return True
    if db.execute(
        "SELECT 1 FROM moderation_holds WHERE journal_id=?", (journal["id"],)
    ).fetchone():
        return False
    if db.execute(
        "SELECT suspended FROM users WHERE id=?", (journal["author_id"],)
    ).fetchone()[0]:
        return False
    if journal["audience"] == "community":
        if db.execute(
            "SELECT 1 FROM hidden_posts WHERE user_id=? AND journal_id=?",
            (uid, journal["id"]),
        ).fetchone():
            return False
        # Account-level block effects must not identify an anonymous story's writer.
        return bool(journal["anonymous"]) or not blocked(db, uid, journal["author_id"])
    if blocked(db, uid, journal["author_id"]):
        return False
    if journal["audience"] == "companion":
        connection = active(db, uid)
        return connection is not None and connection["id"] == journal["connection_id"]
    return False


def get_journal(db, jid, uid):
    row = db.execute("SELECT * FROM journals WHERE id=?", (identifier(jid),)).fetchone()
    if row is None or not readable(db, row, uid):
        fail("This post could not be found.", 404)
    return row
