"""SQLite schema, migrations, and transaction boundaries."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .constants import LEGACY_SUPPORT

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL);
INSERT OR IGNORE INTO meta VALUES(1,0);
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 nickname TEXT NOT NULL, birth_date TEXT NOT NULL, age_verified INTEGER NOT NULL DEFAULT 0,
 symbol TEXT NOT NULL DEFAULT 'leaf.fill', bio TEXT NOT NULL DEFAULT '',
 interests TEXT NOT NULL DEFAULT '["Music","Reading"]',
 support TEXT NOT NULL DEFAULT 'listen', pace TEXT NOT NULL DEFAULT 'Evenings',
 suspended INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires);
CREATE TABLE IF NOT EXISTS connections (
 id TEXT PRIMARY KEY, first_id TEXT NOT NULL REFERENCES users(id), second_id TEXT NOT NULL REFERENCES users(id),
 started REAL NOT NULL, ended REAL, paused INTEGER NOT NULL DEFAULT 0,
 total_days INTEGER NOT NULL DEFAULT 0, best_streak INTEGER NOT NULL DEFAULT 0,
 streak INTEGER NOT NULL DEFAULT 0, last_complete_day TEXT);
CREATE INDEX IF NOT EXISTS connections_first ON connections(first_id,ended);
CREATE INDEX IF NOT EXISTS connections_second ON connections(second_id,ended);
CREATE TABLE IF NOT EXISTS journals (
 id TEXT PRIMARY KEY, author_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL, body TEXT NOT NULL,
 shared_text TEXT NOT NULL, audience TEXT NOT NULL CHECK(audience IN ('privateOnly','companion','community')),
 connection_id TEXT REFERENCES connections(id), anonymous INTEGER NOT NULL, comments_enabled INTEGER NOT NULL,
 support TEXT NOT NULL, created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS journals_owner ON journals(author_id,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS journals_feed ON journals(audience,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS journals_connection ON journals(connection_id,audience);
CREATE TABLE IF NOT EXISTS moderation_holds (
 journal_id TEXT PRIMARY KEY REFERENCES journals(id) ON DELETE CASCADE,
 actor_id TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS hidden_posts (
 user_id TEXT NOT NULL REFERENCES users(id), journal_id TEXT NOT NULL REFERENCES journals(id) ON DELETE CASCADE,
 PRIMARY KEY(user_id,journal_id));
CREATE TABLE IF NOT EXISTS invitations (
 id TEXT PRIMARY KEY, sender_id TEXT NOT NULL REFERENCES users(id), recipient_id TEXT NOT NULL REFERENCES users(id),
 source_journal_id TEXT REFERENCES journals(id) ON DELETE SET NULL, source_alias TEXT, created REAL NOT NULL,
 UNIQUE(sender_id,recipient_id));
CREATE INDEX IF NOT EXISTS invitations_recipient ON invitations(recipient_id);
CREATE TABLE IF NOT EXISTS comments (
 id TEXT PRIMARY KEY, journal_id TEXT NOT NULL REFERENCES journals(id) ON DELETE CASCADE,
 author_id TEXT NOT NULL REFERENCES users(id), text TEXT NOT NULL, created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS comments_journal ON comments(journal_id,created DESC,id DESC);
CREATE TABLE IF NOT EXISTS listening (
 journal_id TEXT NOT NULL REFERENCES journals(id) ON DELETE CASCADE, user_id TEXT NOT NULL REFERENCES users(id),
 PRIMARY KEY(journal_id,user_id));
CREATE TABLE IF NOT EXISTS messages (
 id TEXT PRIMARY KEY, connection_id TEXT NOT NULL REFERENCES connections(id),
 sender_id TEXT NOT NULL REFERENCES users(id), text TEXT NOT NULL, created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS messages_connection ON messages(connection_id,created DESC,id DESC);
CREATE TABLE IF NOT EXISTS checkins (
 connection_id TEXT NOT NULL REFERENCES connections(id), user_id TEXT NOT NULL REFERENCES users(id),
 day TEXT NOT NULL, PRIMARY KEY(connection_id,day,user_id));
CREATE TABLE IF NOT EXISTS blocks (
 blocker_id TEXT NOT NULL REFERENCES users(id), blocked_id TEXT NOT NULL REFERENCES users(id),
 PRIMARY KEY(blocker_id,blocked_id));
CREATE INDEX IF NOT EXISTS blocks_reverse ON blocks(blocked_id,blocker_id);
CREATE TABLE IF NOT EXISTS reports (
 id TEXT PRIMARY KEY, reporter_id TEXT NOT NULL REFERENCES users(id), reported_id TEXT NOT NULL REFERENCES users(id),
 reason TEXT NOT NULL, created REAL NOT NULL, status TEXT NOT NULL DEFAULT 'open');
CREATE TABLE IF NOT EXISTS requests (
 user_id TEXT NOT NULL REFERENCES users(id), request_id TEXT NOT NULL, payload_hash TEXT NOT NULL,
 result TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(user_id,request_id));
CREATE INDEX IF NOT EXISTS requests_expiry ON requests(created);
CREATE INDEX IF NOT EXISTS reports_queue ON reports(status,created DESC,id DESC);
CREATE INDEX IF NOT EXISTS users_created ON users(created DESC,id DESC);
CREATE TABLE IF NOT EXISTS audit_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id TEXT NOT NULL, action TEXT NOT NULL,
 target_id TEXT NOT NULL, detail TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS encryption_keys (
 user_id TEXT PRIMARY KEY REFERENCES users(id), agreement_key TEXT NOT NULL,
 signing_key TEXT NOT NULL, fingerprint TEXT NOT NULL, wrapped_private TEXT NOT NULL,
 nonce TEXT NOT NULL, created REAL NOT NULL);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # WAL configuration must precede any explicit transaction.
        with sqlite3.connect(str(self.path), timeout=5) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3, 4, 5):
                raise RuntimeError(
                    "Unsupported database schema. Back up before upgrading."
                )
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            # Re-read under the write lock: CLI and server may start together.
            db.execute("BEGIN IMMEDIATE")
            if db.execute("PRAGMA user_version").fetchone()[0] < 2:
                db.execute(
                    "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','moderator','admin'))"
                )
                db.execute(
                    "ALTER TABLE reports ADD COLUMN journal_id TEXT REFERENCES journals(id) ON DELETE SET NULL"
                )
                db.execute(
                    "ALTER TABLE reports ADD COLUMN evidence TEXT NOT NULL DEFAULT ''"
                )
                db.execute(
                    "ALTER TABLE reports ADD COLUMN review_note TEXT NOT NULL DEFAULT ''"
                )
                db.execute("ALTER TABLE reports ADD COLUMN reviewer_id TEXT")
                db.execute("ALTER TABLE reports ADD COLUMN reviewed_at REAL")
                db.execute("PRAGMA user_version=2")
            if db.execute("PRAGMA user_version").fetchone()[0] < 3:
                # Legacy anonymous invitations linked an alias to named-account actions.
                db.execute("""DELETE FROM invitations WHERE source_alias IS NOT NULL OR source_journal_id IN
                              (SELECT id FROM journals WHERE anonymous=1)""")
                # Preserve staff decisions made before durable moderation holds existed.
                for actor, detail, created in db.execute(
                    "SELECT actor_id,detail,created FROM audit_log WHERE action='report.hide' ORDER BY id"
                ):
                    jid = json.loads(detail).get("journalID")
                    db.execute(
                        """INSERT OR IGNORE INTO moderation_holds SELECT id,?,? FROM journals WHERE id=?""",
                        (actor, created, jid),
                    )
                db.execute(
                    "UPDATE journals SET audience='privateOnly',shared_text='',connection_id=NULL WHERE id IN (SELECT journal_id FROM moderation_holds)"
                )
                db.execute(
                    "DELETE FROM comments WHERE journal_id IN (SELECT journal_id FROM moderation_holds)"
                )
                db.execute(
                    "DELETE FROM listening WHERE journal_id IN (SELECT journal_id FROM moderation_holds)"
                )
                db.execute("PRAGMA user_version=3")
            if db.execute("PRAGMA user_version").fetchone()[0] < 4:
                for legacy, canonical in LEGACY_SUPPORT.items():
                    db.execute(
                        "UPDATE users SET support=? WHERE support=?",
                        (canonical, legacy),
                    )
                    db.execute(
                        "UPDATE journals SET support=? WHERE support=?",
                        (canonical, legacy),
                    )
                db.execute("PRAGMA user_version=4")
                changed(db)
            if db.execute("PRAGMA user_version").fetchone()[0] < 5:
                if not any(
                    row[1] == "deleted_at"
                    for row in db.execute("PRAGMA table_info(users)")
                ):
                    db.execute("ALTER TABLE users ADD COLUMN deleted_at REAL")
                db.execute("PRAGMA user_version=5")
        db.close()

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(str(self.path), timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("PRAGMA cache_size=-2048")
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()


def changed(db):
    db.execute("UPDATE meta SET revision=revision+1 WHERE id=1")
