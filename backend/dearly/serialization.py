"""Bounded snapshots and DTOs with explicit privacy boundaries."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from .constants import ROLE_PERMISSIONS, SWIFT_EPOCH
from .policies import active, blocked, can_invite
from .validation import age_on


def profile_dto(row, now):
    return dict(
        id=row["id"],
        nickname=row["nickname"],
        age=0
        if row["deleted_at"] is not None
        else age_on(
            row["birth_date"], datetime.fromtimestamp(now, timezone.utc).date()
        ),
        ageVerified=bool(row["age_verified"]),
        symbol=row["symbol"],
        bio=row["bio"],
        interests=json.loads(row["interests"]),
        support=row["support"],
        pace=row["pace"],
    )


def alias_profile(jid):
    return dict(
        id=jid,
        nickname="A friend",
        age=0,
        ageVerified=False,
        symbol="sparkles",
        bio="",
        interests=[],
        support="listen",
        pace="",
    )


def journal_dto(db, row, uid, now):
    own = row["author_id"] == uid
    anonymous = bool(row["anonymous"]) and row["audience"] == "community"
    author = row["id"] if anonymous and not own else row["author_id"]
    listening = db.execute(
        "SELECT 1 FROM listening WHERE journal_id=? AND user_id=?", (row["id"], uid)
    ).fetchone()
    return dict(
        id=row["id"],
        authorID=author,
        title=row["title"] if own else "",
        body=row["body"] if own else "",
        sharedText=row["shared_text"],
        audience=row["audience"],
        connectionID=row["connection_id"],
        anonymous=bool(row["anonymous"]) if own else anonymous,
        commentsEnabled=bool(row["comments_enabled"]),
        support=row["support"],
        date=row["created"] - SWIFT_EPOCH,
        listeners=[uid] if listening else [],
        canInviteAuthor=False
        if anonymous
        else can_invite(db, uid, row["author_id"], now),
        moderationHidden=bool(
            db.execute(
                "SELECT 1 FROM moderation_holds WHERE journal_id=?", (row["id"],)
            ).fetchone()
        )
        if own
        else False,
    )


def connection_dto(db, row, now):
    today = datetime.fromtimestamp(now, timezone.utc).date()
    streak = row["streak"]
    if (
        row["last_complete_day"] is None
        or (today - date.fromisoformat(row["last_complete_day"])).days > 1
    ):
        streak = 0
    checks = db.execute(
        "SELECT user_id FROM checkins WHERE connection_id=? AND day=?",
        (row["id"], today.isoformat()),
    ).fetchall()
    return dict(
        id=row["id"],
        members=[row["first_id"], row["second_id"]],
        startedAt=row["started"] - SWIFT_EPOCH,
        endedAt=row["ended"] - SWIFT_EPOCH if row["ended"] is not None else None,
        paused=bool(row["paused"]),
        checkIns={today.isoformat(): [r["user_id"] for r in checks]},
        bestStreak=row["best_streak"],
        serverTotalDays=row["total_days"],
        serverCurrentStreak=streak,
    )


def message_dto(row):
    return dict(
        id=row["id"],
        connectionID=row["connection_id"],
        senderID=row["sender_id"],
        text=row["text"],
        date=row["created"] - SWIFT_EPOCH,
    )


def snapshot(db, user, now, limit=60):
    uid = user["id"]
    profile_ids = {uid}
    aliases = {}
    # Bounded indexed windows. No other user's private body is serialized.
    own = db.execute(
        "SELECT * FROM journals WHERE author_id=? ORDER BY created DESC,id DESC LIMIT ?",
        (uid, limit),
    ).fetchall()
    feed = db.execute(
        """SELECT j.* FROM journals j JOIN users u ON u.id=j.author_id
       WHERE j.audience='community' AND u.suspended=0
       AND NOT EXISTS(SELECT 1 FROM moderation_holds h WHERE h.journal_id=j.id)
       AND NOT EXISTS(SELECT 1 FROM hidden_posts h WHERE h.user_id=? AND h.journal_id=j.id)
       AND (j.anonymous=1 OR NOT EXISTS(SELECT 1 FROM blocks b WHERE (b.blocker_id=? AND b.blocked_id=j.author_id) OR (b.blocker_id=j.author_id AND b.blocked_id=?)))
       ORDER BY j.created DESC,j.id DESC LIMIT ?""",
        (uid, uid, uid, limit),
    ).fetchall()
    conn = active(db, uid)
    shared = (
        db.execute(
            "SELECT * FROM journals WHERE connection_id=? AND audience='companion' ORDER BY created DESC,id DESC LIMIT ?",
            (conn["id"], limit),
        ).fetchall()
        if conn
        else []
    )
    journals = {r["id"]: r for r in own + feed + shared}
    journal_data = []
    for row in journals.values():
        dto = journal_dto(db, row, uid, now)
        journal_data.append(dto)
        if dto["authorID"] != row["author_id"]:
            aliases[dto["authorID"]] = alias_profile(dto["authorID"])
        else:
            profile_ids.add(row["author_id"])
    connections = db.execute(
        "SELECT * FROM connections WHERE first_id=? OR second_id=? ORDER BY started DESC LIMIT 20",
        (uid, uid),
    ).fetchall()
    if conn is not None and all(c["id"] != conn["id"] for c in connections):
        connections.append(conn)
    for c in connections:
        profile_ids.update([c["first_id"], c["second_id"]])
    invitations = []
    for row in db.execute(
        "SELECT * FROM invitations WHERE sender_id=? OR recipient_id=? ORDER BY created DESC LIMIT 100",
        (uid, uid),
    ):
        recipient = row["recipient_id"]
        source = db.execute(
            "SELECT * FROM journals WHERE id=?", (row["source_journal_id"],)
        ).fetchone()
        if row["source_alias"] or (source and source["anonymous"]):
            continue
        profile_ids.add(recipient)
        profile_ids.add(row["sender_id"])
        invitations.append(
            dict(
                id=row["id"],
                senderID=row["sender_id"],
                recipientID=recipient,
                date=row["created"] - SWIFT_EPOCH,
            )
        )
    # Candidate selection excludes active users and blocked edges before its bounded scan.
    today = datetime.fromtimestamp(now, timezone.utc).date()
    try:
        eighteenth = today.replace(year=today.year - 18).isoformat()
    except ValueError:
        eighteenth = today.replace(year=today.year - 18, day=28).isoformat()
    own_age = age_on(user["birth_date"], today)
    age_clause = "u.birth_date>?" if own_age < 18 else "u.birth_date<=?"
    candidates = (
        db.execute(
            f"""SELECT u.* FROM users u WHERE u.id!=? AND u.age_verified=1 AND u.suspended=0 AND {age_clause}
      AND NOT EXISTS(SELECT 1 FROM connections c WHERE c.ended IS NULL AND (c.first_id=u.id OR c.second_id=u.id))
      AND NOT EXISTS(SELECT 1 FROM blocks b WHERE (b.blocker_id=? AND b.blocked_id=u.id) OR (b.blocker_id=u.id AND b.blocked_id=?))
      ORDER BY u.created DESC LIMIT 100""",
            (uid, eighteenth, uid, uid),
        ).fetchall()
        if user["age_verified"] and conn is None
        else []
    )
    suggestion_ids = []
    for row in candidates:
        if can_invite(db, uid, row["id"], now):
            profile_ids.add(row["id"])
            suggestion_ids.append(row["id"])
    comments = []
    public_ids = [r["id"] for r in journals.values() if r["audience"] == "community"]
    if public_ids:
        marks = ",".join("?" for _ in public_ids)
        rows = db.execute(
            f"""SELECT c.* FROM comments c JOIN users u ON u.id=c.author_id
                            WHERE c.journal_id IN ({marks}) AND u.suspended=0 ORDER BY c.created DESC,c.id DESC LIMIT 200""",
            public_ids,
        ).fetchall()
        for row in reversed(rows):
            journal = journals[row["journal_id"]]
            hide = (
                journal["anonymous"]
                and row["author_id"] == journal["author_id"]
                and uid != row["author_id"]
            )
            if not hide and blocked(db, uid, row["author_id"]):
                continue
            author = journal["id"] if hide else row["author_id"]
            if hide:
                aliases[author] = alias_profile(author)
            else:
                profile_ids.add(author)
            comments.append(
                dict(
                    id=row["id"],
                    journalID=row["journal_id"],
                    authorID=author,
                    text=row["text"],
                    date=row["created"] - SWIFT_EPOCH,
                )
            )
    marks = ",".join("?" for _ in profile_ids)
    profiles = [
        profile_dto(r, now)
        for r in db.execute(
            f"SELECT * FROM users WHERE id IN ({marks})", list(profile_ids)
        )
    ]
    profiles.extend(aliases.values())
    messages = (
        db.execute(
            "SELECT * FROM messages WHERE connection_id=? ORDER BY created DESC,id DESC LIMIT 100",
            (conn["id"],),
        ).fetchall()
        if conn
        else []
    )
    blockrows = db.execute(
        f"SELECT * FROM blocks WHERE (blocker_id=? OR blocked_id=?) AND blocker_id IN ({marks}) AND blocked_id IN ({marks})",
        (uid, uid, *profile_ids, *profile_ids),
    ).fetchall()
    return dict(
        schemaVersion=1,
        profiles=profiles,
        currentUserID=uid,
        journals=journal_data,
        comments=comments,
        invitations=invitations,
        connections=[connection_dto(db, r, now) for r in connections],
        messages=[message_dto(r) for r in reversed(messages)],
        blocks=[
            dict(blockerID=r["blocker_id"], blockedID=r["blocked_id"])
            for r in blockrows
        ],
        reports=[],
        demoDayOffset=0,
        suggestedUserIDs=suggestion_ids,
        currentUserRole=user["role"],
        permissions=sorted(ROLE_PERMISSIONS.get(user["role"], ())),
    )


def staff_report_dto(db, row):
    journal = db.execute(
        """SELECT 1 FROM journals j WHERE id=? AND author_id=? AND audience='community'
                            AND NOT EXISTS(SELECT 1 FROM moderation_holds h WHERE h.journal_id=j.id)""",
        (row["journal_id"], row["reported_id"]),
    ).fetchone()
    names = {
        r["id"]: r["nickname"]
        for r in db.execute(
            "SELECT id,nickname FROM users WHERE id IN (?,?)",
            (row["reporter_id"], row["reported_id"]),
        )
    }
    return dict(
        id=row["id"],
        reporterID=row["reporter_id"],
        reportedID=row["reported_id"],
        reporterNickname=names[row["reporter_id"]],
        reportedNickname=names[row["reported_id"]],
        reason=row["reason"],
        status=row["status"],
        date=row["created"] - SWIFT_EPOCH,
        journalID=row["journal_id"],
        evidence=row["evidence"],
        canHide=bool(journal),
        canRestore=bool(
            db.execute(
                "SELECT 1 FROM moderation_holds WHERE journal_id=?",
                (row["journal_id"],),
            ).fetchone()
        ),
        reviewNote=row["review_note"],
        reviewerID=row["reviewer_id"],
        reviewedAt=row["reviewed_at"] - SWIFT_EPOCH
        if row["reviewed_at"] is not None
        else None,
    )
