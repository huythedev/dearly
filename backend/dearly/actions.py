"""Transactional journal, connection, chat, and profile mutations."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from .moderation import apply_staff_action
from .encryption import validate_content
from .policies import active, can_invite, eligible, get_journal
from .validation import bool_field, fail, identifier, new_id, support_field, text_field


def apply_action(db, user, kind, p, now):
    uid = user["id"]
    if kind.startswith("staff."):
        return apply_staff_action(db, user, kind, p, now)
    if kind == "journal.save":
        jid = (
            identifier(p.get("id") or p.get("clientID"))
            if p.get("id") or p.get("clientID")
            else new_id()
        )
        old = db.execute("SELECT * FROM journals WHERE id=?", (jid,)).fetchone()
        if old and old["author_id"] != uid:
            fail("You cannot edit this post.", 403)
        if p.get("id") and old is None:
            fail("The journal entry to edit could not be found.", 404)
        if p.get("clientID") and old is not None:
            fail("This journal ID already exists.", 409)
        sealed_body = isinstance(p.get("body"), str) and p["body"].startswith(
            "dearly:e2ee:1:"
        )
        body = text_field(p, "body", 180000 if sealed_body else 20000)
        encrypted = validate_content(
            db, body, purpose="journal", resource=jid, sender=uid, members=[uid]
        )
        if not encrypted and len(body) > 20000:
            fail("Journal entries can contain up to 20000 characters.")
        title = text_field(p, "title", 160, default="", empty=True)
        if encrypted and title:
            fail("Put the title inside the encrypted journal.")
        audience = p.get("audience", "privateOnly")
        if audience not in ("privateOnly", "companion", "community"):
            fail("Invalid sharing option.")
        if (
            audience != "privateOnly"
            and db.execute(
                "SELECT 1 FROM moderation_holds WHERE journal_id=?", (jid,)
            ).fetchone()
        ):
            fail(
                "Sharing is restricted for this entry. You can still save privately; contact staff for a review.",
                403,
            )
        excerpt = text_field(p, "sharedText", 120000, default="", empty=True)
        if audience != "privateOnly" and (
            not excerpt or (not encrypted and excerpt not in body)
        ):
            fail("The shared passage must be part of your journal entry.")
        support = support_field(p)
        conn = active(db, uid) if audience == "companion" else None
        if audience == "companion" and conn is None:
            fail("You don’t have a connection yet.")
        if conn and not eligible(db, conn["first_id"], conn["second_id"], now):
            fail("The age groups for this connection need to be reviewed.", 403)
        if conn:
            sealed = validate_content(
                db,
                excerpt,
                purpose="passage",
                resource=jid,
                sender=uid,
                members=[conn["first_id"], conn["second_id"]],
                connection=conn["id"],
            )
            if sealed != encrypted:
                fail("Encrypt both the journal and the shared passage.")
        if audience == "community" and (
            len(excerpt) > 20000 or excerpt.startswith("dearly:e2ee:")
        ):
            fail("Community passages must be readable and at most 20000 characters.")
        values = (
            jid,
            uid,
            title,
            body,
            excerpt if audience != "privateOnly" else "",
            audience,
            conn["id"] if conn else None,
            int(bool_field(p, "anonymous")),
            int(bool_field(p, "commentsEnabled", True)),
            support,
            old["created"] if old else now,
        )
        db.execute(
            """INSERT INTO journals VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
          title=excluded.title,body=excluded.body,shared_text=excluded.shared_text,audience=excluded.audience,
          connection_id=excluded.connection_id,anonymous=excluded.anonymous,comments_enabled=excluded.comments_enabled,support=excluded.support""",
            values,
        )
        if audience != "community":
            db.execute("DELETE FROM comments WHERE journal_id=?", (jid,))
            db.execute("DELETE FROM listening WHERE journal_id=?", (jid,))
        if bool_field(p, "anonymous"):
            db.execute("DELETE FROM invitations WHERE source_journal_id=?", (jid,))
        return {"id": jid}
    if kind == "journal.hide":
        row = get_journal(db, p.get("id"), uid)
        if row["audience"] != "community" or row["author_id"] == uid:
            fail("You can only hide another person’s community post.", 400)
        db.execute("INSERT OR IGNORE INTO hidden_posts VALUES(?,?)", (uid, row["id"]))
        return {}
    if kind == "journal.delete":
        row = get_journal(db, p.get("id"), uid)
        if row["author_id"] != uid:
            fail("You cannot delete this post.", 403)
        db.execute("DELETE FROM journals WHERE id=?", (row["id"],))
        return {}
    if kind in ("journal.listen", "journal.comment"):
        row = get_journal(db, p.get("id"), uid)
        if row["audience"] != "community":
            fail("This post is private.", 403)
        if kind == "journal.listen":
            if row["author_id"] == uid:
                fail("You cannot react to your own post.")
            enabled = bool_field(p, "enabled", True)
            if enabled:
                db.execute(
                    "INSERT OR IGNORE INTO listening VALUES(?,?)", (row["id"], uid)
                )
            else:
                db.execute(
                    "DELETE FROM listening WHERE journal_id=? AND user_id=?",
                    (row["id"], uid),
                )
        else:
            if not row["comments_enabled"]:
                fail("Responses are turned off for this post.", 403)
            db.execute(
                "INSERT INTO comments VALUES(?,?,?,?,?)",
                (new_id(), row["id"], uid, text_field(p, "text", 2000), now),
            )
        return {}
    if kind == "invitation.send":
        source = None
        if p.get("journalID"):
            source = get_journal(db, p["journalID"], uid)
            if source["anonymous"]:
                fail(
                    "Anonymous stories do not accept invitations. Connect through a shared profile.",
                    403,
                )
            if source["audience"] != "community":
                fail("This post does not accept invitations.", 403)
            target = source["author_id"]
        else:
            target = identifier(p.get("userID"))
        if not can_invite(db, uid, target, now):
            fail(
                "Both people need verified ages, compatible age groups, and no current connection.",
                403,
            )
        if db.execute(
            "SELECT 1 FROM invitations WHERE (sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?)",
            (uid, target, target, uid),
        ).fetchone():
            fail("An invitation already exists between you.", 409)
        if (
            db.execute(
                "SELECT count(*) FROM invitations WHERE sender_id=?", (uid,)
            ).fetchone()[0]
            >= 20
        ):
            fail("You can have up to 20 pending invitations.", 409)
        iid = new_id()
        db.execute(
            "INSERT INTO invitations VALUES(?,?,?,?,?,?)",
            (
                iid,
                uid,
                target,
                source["id"] if source else None,
                source["id"] if source and source["anonymous"] else None,
                now,
            ),
        )
        return {"id": iid}
    if kind in ("invitation.accept", "invitation.dismiss"):
        row = db.execute(
            "SELECT * FROM invitations WHERE id=?", (identifier(p.get("id")),)
        ).fetchone()
        if row is None or uid not in (row["sender_id"], row["recipient_id"]):
            fail("This invitation could not be found.", 404)
        if kind == "invitation.accept":
            if row["recipient_id"] != uid:
                fail("Only the recipient can accept an invitation.", 403)
            a, b = row["sender_id"], row["recipient_id"]
            if not can_invite(db, a, b, now):
                fail(
                    "This connection is no longer eligible, or someone has another connection.",
                    409,
                )
            cid = new_id()
            db.execute(
                "INSERT INTO connections(id,first_id,second_id,started) VALUES(?,?,?,?)",
                (cid, a, b, now),
            )
            db.execute(
                "DELETE FROM invitations WHERE sender_id IN (?,?) OR recipient_id IN (?,?)",
                (a, b, a, b),
            )
            return {"id": cid}
        db.execute("DELETE FROM invitations WHERE id=?", (row["id"],))
        return {}
    if kind in (
        "message.send",
        "connection.checkin",
        "connection.pause",
        "connection.leave",
    ):
        conn = active(db, uid)
        if conn is None or conn["id"] != identifier(p.get("connectionID")):
            fail("This connection is no longer active.", 409)
        cid = conn["id"]
        if kind != "connection.leave" and not eligible(
            db, conn["first_id"], conn["second_id"], now
        ):
            fail("The age groups for this connection need to be reviewed.", 403)
        if kind == "message.send":
            mid = identifier(p["clientID"]) if p.get("clientID") else new_id()
            text = text_field(p, "text", 26000)
            encrypted = validate_content(
                db,
                text,
                purpose="message",
                resource=mid,
                sender=uid,
                members=[conn["first_id"], conn["second_id"]],
                connection=cid,
            )
            if not encrypted and len(text) > 4000:
                fail("Messages can contain up to 4000 characters.")
            if db.execute("SELECT 1 FROM messages WHERE id=?", (mid,)).fetchone():
                fail("This message ID already exists.", 409)
            db.execute(
                "INSERT INTO messages VALUES(?,?,?,?,?)",
                (mid, cid, uid, text, now),
            )
            return {"id": mid}
        if kind == "connection.leave":
            db.execute("UPDATE connections SET ended=? WHERE id=?", (now, cid))
        if kind == "connection.pause":
            db.execute(
                "UPDATE connections SET paused=? WHERE id=?",
                (int(bool_field(p, "paused")), cid),
            )
        if kind == "connection.checkin":
            if conn["paused"]:
                fail("The garden is resting.", 409)
            today = datetime.fromtimestamp(now, timezone.utc).date()
            key = today.isoformat()
            db.execute("INSERT OR IGNORE INTO checkins VALUES(?,?,?)", (cid, uid, key))
            count = db.execute(
                "SELECT count(*) FROM checkins WHERE connection_id=? AND day=?",
                (cid, key),
            ).fetchone()[0]
            if count == 2 and conn["last_complete_day"] != key:
                streak = (
                    conn["streak"] + 1
                    if conn["last_complete_day"]
                    == (today - timedelta(days=1)).isoformat()
                    else 1
                )
                db.execute(
                    "UPDATE connections SET total_days=total_days+1,streak=?,best_streak=max(best_streak,?),last_complete_day=? WHERE id=?",
                    (streak, streak, key, cid),
                )
        return {}
    if kind in ("user.block", "report.create"):
        source = None
        if p.get("journalID"):
            source = get_journal(db, p["journalID"], uid)
            target = source["author_id"]
            if (
                kind == "user.block"
                and source["anonymous"]
                and source["audience"] == "community"
            ):
                # Compatibility for old clients: hide this story without a named-account side effect.
                if target == uid:
                    fail("You cannot hide your own post.")
                db.execute(
                    "INSERT OR IGNORE INTO hidden_posts VALUES(?,?)",
                    (uid, source["id"]),
                )
                return {}
        else:
            target = identifier(p.get("userID"))
        if (
            target == uid
            or db.execute("SELECT 1 FROM users WHERE id=?", (target,)).fetchone()
            is None
        ):
            fail("Invalid user.")
        if kind == "user.block":
            db.execute("INSERT OR IGNORE INTO blocks VALUES(?,?)", (uid, target))
            db.execute(
                "DELETE FROM invitations WHERE (sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?)",
                (uid, target, target, uid),
            )
            db.execute(
                "UPDATE connections SET ended=? WHERE ended IS NULL AND ((first_id=? AND second_id=?) OR (first_id=? AND second_id=?))",
                (now, uid, target, target, uid),
            )
        else:
            # Preserve only the excerpt explicitly published to the community, never a private body/chat.
            public = source is not None and source["audience"] == "community"
            db.execute(
                "INSERT INTO reports(id,reporter_id,reported_id,reason,created,journal_id,evidence) VALUES(?,?,?,?,?,?,?)",
                (
                    new_id(),
                    uid,
                    target,
                    text_field(p, "reason", 1000),
                    now,
                    source["id"] if public else None,
                    source["shared_text"] if public else "",
                ),
            )
        return {}
    if kind == "profile.update":
        nickname = text_field(p, "nickname", 40)
        bio = text_field(p, "bio", 500, default="", empty=True)
        interests = p.get("interests", [])
        if (
            not isinstance(interests, list)
            or len(interests) > 8
            or any(
                not isinstance(x, str) or not 1 <= len(x.strip()) <= 30
                for x in interests
            )
        ):
            fail("Choose up to 8 interests, each between 1 and 30 characters.")
        support = support_field(p)
        pace = text_field(p, "pace", 80, default="Evenings")
        db.execute(
            "UPDATE users SET nickname=?,bio=?,interests=?,support=?,pace=? WHERE id=?",
            (
                nickname,
                bio,
                json.dumps([x.strip() for x in interests], ensure_ascii=False),
                support,
                pace,
                uid,
            ),
        )
        return {}
    fail("This action is not supported.")
