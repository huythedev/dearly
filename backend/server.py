"""Dearly single-node API. Python 3.11+, SQLite, standard asyncio on every OS."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import contextmanager, asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
import anyio
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from localization import RequestError, error_response
from realtime import ChatHub
from web_support import BrowserSession, COOKIE, browser_session, mount_web, same_origin

SWIFT_EPOCH = 978307200  # Swift JSONEncoder default: seconds since 2001-01-01 UTC.
SUPPORT = frozenset({'listen', 'relate', 'brainstorm'})
# Compatibility input only; new storage and DTOs use the identifiers above.
LEGACY_SUPPORT = {'Chỉ cần lắng nghe': 'listen', 'Chia sẻ trải nghiệm': 'relate', 'Cùng nghĩ cách': 'brainstorm'}
ROLE_PERMISSIONS = {
    'user': frozenset(),
    'moderator': frozenset({'reports.read', 'reports.review', 'reports.hide'}),
    'admin': frozenset({'reports.read', 'reports.review', 'reports.hide', 'users.read',
                        'users.suspend', 'users.verify_age', 'roles.manage', 'audit.read'}),
}
STAFF_ACTIONS = {'staff.report.review': 'reports.review', 'staff.report.hide': 'reports.hide',
                 'staff.report.restore': 'reports.hide',
                 'staff.user.suspend': 'users.suspend', 'staff.user.verify_age': 'users.verify_age',
                 'staff.user.role': 'roles.manage'}
SCHEMA = '''
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
'''


def fail(message: str, status: int = 400, **parameters):
    raise RequestError(message, status, **parameters)


def support_field(payload: dict) -> str:
    value = text_field(payload, 'support', 80, default='listen')
    value = LEGACY_SUPPORT.get(value, value)
    if value not in SUPPORT:
        fail('Invalid support preference.')
    return value


def identifier(value) -> str:
    try:
        return str(uuid.UUID(str(value))).upper()
    except (ValueError, TypeError, AttributeError):
        fail('Invalid ID.')


def new_id() -> str:
    return str(uuid.uuid4()).upper()


def text_field(payload: dict, key: str, maximum: int, *, default=None, empty=False) -> str:
    value = payload.get(key, default)
    if not isinstance(value, str):
        fail('Missing or invalid field {field}.', field=key)
    value = value.strip()
    if (not value and not empty) or len(value) > maximum:
        fail('{field}: use between {minimum} and {maximum} characters.', field=key, minimum=0 if empty else 1, maximum=maximum)
    return value


def bool_field(payload, key, default=False):
    value = payload.get(key, default)
    if not isinstance(value, bool):
        fail('{field} must be true/false.', field=key)
    return value


def age_on(birth_date: str, today: date) -> int:
    born = date.fromisoformat(birth_date)
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def validate_birth(value: str, now: float) -> str:
    try:
        born = date.fromisoformat(value)
        age = age_on(born.isoformat(), datetime.fromtimestamp(now, timezone.utc).date())
    except (TypeError, ValueError):
        fail('Invalid date of birth.')
    if not 16 <= age <= 100:
        fail('Accounts are available for ages 16 through 100.')
    return born.isoformat()


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600_000)
    return f'pbkdf2-sha256$600000${salt.hex()}${digest.hex()}'


def password_matches(password: str, encoded: str) -> bool:
    _, rounds, salt, expected = encoded.split('$')
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds))
    return hmac.compare_digest(digest.hex(), expected)


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # WAL configuration must precede any explicit transaction.
        with sqlite3.connect(str(self.path), timeout=5) as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2, 3, 4):
                raise RuntimeError('Unsupported database schema. Back up before upgrading.')
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)
            # Re-read under the write lock: CLI and server may start together.
            db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA user_version').fetchone()[0] < 2:
                db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','moderator','admin'))")
                db.execute('ALTER TABLE reports ADD COLUMN journal_id TEXT REFERENCES journals(id) ON DELETE SET NULL')
                db.execute("ALTER TABLE reports ADD COLUMN evidence TEXT NOT NULL DEFAULT ''")
                db.execute("ALTER TABLE reports ADD COLUMN review_note TEXT NOT NULL DEFAULT ''")
                db.execute('ALTER TABLE reports ADD COLUMN reviewer_id TEXT')
                db.execute('ALTER TABLE reports ADD COLUMN reviewed_at REAL')
                db.execute('PRAGMA user_version=2')
            if db.execute('PRAGMA user_version').fetchone()[0] < 3:
                # Legacy anonymous invitations linked an alias to named-account actions.
                db.execute('''DELETE FROM invitations WHERE source_alias IS NOT NULL OR source_journal_id IN
                              (SELECT id FROM journals WHERE anonymous=1)''')
                # Preserve staff decisions made before durable moderation holds existed.
                for actor, detail, created in db.execute("SELECT actor_id,detail,created FROM audit_log WHERE action='report.hide' ORDER BY id"):
                    jid = json.loads(detail).get('journalID')
                    db.execute('''INSERT OR IGNORE INTO moderation_holds SELECT id,?,? FROM journals WHERE id=?''',
                               (actor, created, jid))
                db.execute("UPDATE journals SET audience='privateOnly',shared_text='',connection_id=NULL WHERE id IN (SELECT journal_id FROM moderation_holds)")
                db.execute('DELETE FROM comments WHERE journal_id IN (SELECT journal_id FROM moderation_holds)')
                db.execute('DELETE FROM listening WHERE journal_id IN (SELECT journal_id FROM moderation_holds)')
                db.execute('PRAGMA user_version=3')
            if db.execute('PRAGMA user_version').fetchone()[0] < 4:
                for legacy, canonical in LEGACY_SUPPORT.items():
                    db.execute('UPDATE users SET support=? WHERE support=?', (canonical, legacy))
                    db.execute('UPDATE journals SET support=? WHERE support=?', (canonical, legacy))
                db.execute('PRAGMA user_version=4')
                changed(db)
        db.close()

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(str(self.path), timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=5000')
        db.execute('PRAGMA cache_size=-2048')
        try:
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()


def changed(db):
    db.execute('UPDATE meta SET revision=revision+1 WHERE id=1')


def blocked(db, a, b):
    return db.execute('SELECT 1 FROM blocks WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)', (a,b,b,a)).fetchone() is not None


def active(db, uid):
    return db.execute('SELECT * FROM connections WHERE ended IS NULL AND (first_id=? OR second_id=?)', (uid,uid)).fetchone()


def eligible(db, a, b, now):
    if a == b or blocked(db, a, b):
        return False
    users = db.execute('SELECT * FROM users WHERE id IN (?,?)', (a,b)).fetchall()
    if len(users) != 2 or any(not u['age_verified'] or u['suspended'] for u in users):
        return False
    today = datetime.fromtimestamp(now, timezone.utc).date()
    ages = [age_on(u['birth_date'], today) for u in users]
    if min(ages) < 16:
        return False
    if min(ages) < 18:
        return max(ages) < 18 and abs(ages[0] - ages[1]) <= 1
    return True


def can_invite(db, a, b, now):
    return eligible(db,a,b,now) and active(db,a) is None and active(db,b) is None


def readable(db, journal, uid):
    if journal['author_id'] == uid:
        return True
    if db.execute('SELECT 1 FROM moderation_holds WHERE journal_id=?', (journal['id'],)).fetchone():
        return False
    if db.execute('SELECT suspended FROM users WHERE id=?', (journal['author_id'],)).fetchone()[0]:
        return False
    if journal['audience'] == 'community':
        if db.execute('SELECT 1 FROM hidden_posts WHERE user_id=? AND journal_id=?', (uid, journal['id'])).fetchone():
            return False
        # Account-level block effects must not identify an anonymous story's writer.
        return bool(journal['anonymous']) or not blocked(db, uid, journal['author_id'])
    if blocked(db,uid,journal['author_id']):
        return False
    if journal['audience'] == 'companion':
        connection = active(db,uid)
        return connection is not None and connection['id'] == journal['connection_id']
    return False


def get_journal(db, jid, uid):
    row = db.execute('SELECT * FROM journals WHERE id=?',(identifier(jid),)).fetchone()
    if row is None or not readable(db,row,uid):
        fail('This post could not be found.',404)
    return row


def profile_dto(row, now):
    return dict(id=row['id'], nickname=row['nickname'], age=age_on(row['birth_date'],datetime.fromtimestamp(now,timezone.utc).date()),
                ageVerified=bool(row['age_verified']), symbol=row['symbol'], bio=row['bio'], interests=json.loads(row['interests']), support=row['support'], pace=row['pace'])


def alias_profile(jid):
    return dict(id=jid,nickname='A friend',age=0,ageVerified=False,symbol='sparkles',bio='',interests=[],support='listen',pace='')


def journal_dto(db, row, uid, now):
    own = row['author_id'] == uid
    anonymous = bool(row['anonymous']) and row['audience'] == 'community'
    author = row['id'] if anonymous and not own else row['author_id']
    listening = db.execute('SELECT 1 FROM listening WHERE journal_id=? AND user_id=?',(row['id'],uid)).fetchone()
    return dict(id=row['id'],authorID=author,title=row['title'] if own else '',body=row['body'] if own else '',
                sharedText=row['shared_text'],audience=row['audience'],connectionID=row['connection_id'],
                anonymous=bool(row['anonymous']) if own else anonymous,
                commentsEnabled=bool(row['comments_enabled']),support=row['support'],date=row['created']-SWIFT_EPOCH,
                listeners=[uid] if listening else [],canInviteAuthor=False if anonymous else can_invite(db,uid,row['author_id'],now),
                moderationHidden=bool(db.execute('SELECT 1 FROM moderation_holds WHERE journal_id=?', (row['id'],)).fetchone()) if own else False)


def connection_dto(db,row,now):
    today = datetime.fromtimestamp(now,timezone.utc).date()
    streak = row['streak']
    if row['last_complete_day'] is None or (today-date.fromisoformat(row['last_complete_day'])).days > 1:
        streak = 0
    checks=db.execute('SELECT user_id FROM checkins WHERE connection_id=? AND day=?',(row['id'],today.isoformat())).fetchall()
    return dict(id=row['id'],members=[row['first_id'],row['second_id']],startedAt=row['started']-SWIFT_EPOCH,
                endedAt=row['ended']-SWIFT_EPOCH if row['ended'] is not None else None,paused=bool(row['paused']),
                checkIns={today.isoformat():[r['user_id'] for r in checks]},bestStreak=row['best_streak'],
                serverTotalDays=row['total_days'],serverCurrentStreak=streak)


def message_dto(row):
    return dict(id=row['id'],connectionID=row['connection_id'],senderID=row['sender_id'],text=row['text'],date=row['created']-SWIFT_EPOCH)


def snapshot(db, user, now, limit=60):
    uid=user['id']; profile_ids={uid}; aliases={}
    # Bounded indexed windows. No other user's private body is serialized.
    own=db.execute('SELECT * FROM journals WHERE author_id=? ORDER BY created DESC,id DESC LIMIT ?', (uid,limit)).fetchall()
    feed=db.execute('''SELECT j.* FROM journals j JOIN users u ON u.id=j.author_id
       WHERE j.audience='community' AND u.suspended=0
       AND NOT EXISTS(SELECT 1 FROM moderation_holds h WHERE h.journal_id=j.id)
       AND NOT EXISTS(SELECT 1 FROM hidden_posts h WHERE h.user_id=? AND h.journal_id=j.id)
       AND (j.anonymous=1 OR NOT EXISTS(SELECT 1 FROM blocks b WHERE (b.blocker_id=? AND b.blocked_id=j.author_id) OR (b.blocker_id=j.author_id AND b.blocked_id=?)))
       ORDER BY j.created DESC,j.id DESC LIMIT ?''',(uid,uid,uid,limit)).fetchall()
    conn=active(db,uid)
    shared=db.execute("SELECT * FROM journals WHERE connection_id=? AND audience='companion' ORDER BY created DESC,id DESC LIMIT ?",(conn['id'],limit)).fetchall() if conn else []
    journals={r['id']:r for r in own+feed+shared}
    journal_data=[]
    for row in journals.values():
        dto=journal_dto(db,row,uid,now); journal_data.append(dto)
        if dto['authorID'] != row['author_id']: aliases[dto['authorID']]=alias_profile(dto['authorID'])
        else: profile_ids.add(row['author_id'])
    connections=db.execute('SELECT * FROM connections WHERE first_id=? OR second_id=? ORDER BY started DESC LIMIT 20',(uid,uid)).fetchall()
    if conn is not None and all(c['id'] != conn['id'] for c in connections):
        connections.append(conn)
    for c in connections: profile_ids.update([c['first_id'],c['second_id']])
    invitations=[]
    for row in db.execute('SELECT * FROM invitations WHERE sender_id=? OR recipient_id=? ORDER BY created DESC LIMIT 100',(uid,uid)):
        recipient=row['recipient_id']
        source=db.execute('SELECT * FROM journals WHERE id=?',(row['source_journal_id'],)).fetchone()
        if row['source_alias'] or (source and source['anonymous']):
            continue
        profile_ids.add(recipient)
        profile_ids.add(row['sender_id'])
        invitations.append(dict(id=row['id'],senderID=row['sender_id'],recipientID=recipient,date=row['created']-SWIFT_EPOCH))
    # Candidate selection excludes active users and blocked edges before its bounded scan.
    today=datetime.fromtimestamp(now,timezone.utc).date()
    try: eighteenth=today.replace(year=today.year-18).isoformat()
    except ValueError: eighteenth=today.replace(year=today.year-18,day=28).isoformat()
    own_age=age_on(user['birth_date'],today)
    age_clause='u.birth_date>?' if own_age<18 else 'u.birth_date<=?'
    candidates=db.execute(f'''SELECT u.* FROM users u WHERE u.id!=? AND u.age_verified=1 AND u.suspended=0 AND {age_clause}
      AND NOT EXISTS(SELECT 1 FROM connections c WHERE c.ended IS NULL AND (c.first_id=u.id OR c.second_id=u.id))
      AND NOT EXISTS(SELECT 1 FROM blocks b WHERE (b.blocker_id=? AND b.blocked_id=u.id) OR (b.blocker_id=u.id AND b.blocked_id=?))
      ORDER BY u.created DESC LIMIT 100''',(uid,eighteenth,uid,uid)).fetchall() if user['age_verified'] and conn is None else []
    suggestion_ids=[]
    for row in candidates:
        if can_invite(db,uid,row['id'],now):
            profile_ids.add(row['id']); suggestion_ids.append(row['id'])
    comments=[]
    public_ids=[r['id'] for r in journals.values() if r['audience']=='community']
    if public_ids:
        marks=','.join('?' for _ in public_ids)
        rows=db.execute(f'''SELECT c.* FROM comments c JOIN users u ON u.id=c.author_id
                            WHERE c.journal_id IN ({marks}) AND u.suspended=0 ORDER BY c.created DESC,c.id DESC LIMIT 200''',public_ids).fetchall()
        for row in reversed(rows):
            journal=journals[row['journal_id']]
            hide=journal['anonymous'] and row['author_id']==journal['author_id'] and uid!=row['author_id']
            if not hide and blocked(db,uid,row['author_id']): continue
            author=journal['id'] if hide else row['author_id']
            if hide: aliases[author]=alias_profile(author)
            else: profile_ids.add(author)
            comments.append(dict(id=row['id'],journalID=row['journal_id'],authorID=author,text=row['text'],date=row['created']-SWIFT_EPOCH))
    marks=','.join('?' for _ in profile_ids)
    profiles=[profile_dto(r,now) for r in db.execute(f'SELECT * FROM users WHERE id IN ({marks})',list(profile_ids))]
    profiles.extend(aliases.values())
    messages=db.execute('SELECT * FROM messages WHERE connection_id=? ORDER BY created DESC,id DESC LIMIT 100',(conn['id'],)).fetchall() if conn else []
    blockrows=db.execute(f'SELECT * FROM blocks WHERE (blocker_id=? OR blocked_id=?) AND blocker_id IN ({marks}) AND blocked_id IN ({marks})',(uid,uid,*profile_ids,*profile_ids)).fetchall()
    return dict(schemaVersion=1,profiles=profiles,currentUserID=uid,journals=journal_data,comments=comments,invitations=invitations,
                connections=[connection_dto(db,r,now) for r in connections],messages=[message_dto(r) for r in reversed(messages)],
                blocks=[dict(blockerID=r['blocker_id'],blockedID=r['blocked_id']) for r in blockrows],reports=[],demoDayOffset=0,suggestedUserIDs=suggestion_ids,
                currentUserRole=user['role'],permissions=sorted(ROLE_PERMISSIONS.get(user['role'],())))


class Credentials(BaseModel):
    model_config=ConfigDict(extra='forbid')
    username: str=Field(min_length=3,max_length=64,pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str=Field(min_length=10,max_length=128)


class Registration(Credentials):
    nickname: str=Field(min_length=1,max_length=40)
    birthDate: str=Field(min_length=10,max_length=10)


class Action(BaseModel):
    model_config=ConfigDict(extra='forbid')
    requestID: str=Field(min_length=36,max_length=36)
    kind: str=Field(max_length=40)
    payload: dict=Field(default_factory=dict)


class Limiter:
    """Bounded per-process token buckets. Deploy the documented single worker."""
    def __init__(self):
        self.items=OrderedDict(); self.lock=threading.Lock()
    def check(self,key,capacity,rate):
        now=time.monotonic()
        with self.lock:
            tokens,last=self.items.pop(key,(float(capacity),now))
            tokens=min(capacity,tokens+(now-last)*rate)
            if tokens<1:
                self.items[key]=(tokens,now)
                fail('Too many requests. Please try again in a moment.',429)
            self.items[key]=(tokens-1,now)
            while len(self.items)>4096: self.items.popitem(last=False)


class BodyLimit:
    """Bound bytes, upload time, and concurrent readers before parsing/authentication."""
    def __init__(self, app, idle_timeout=5.0, total_timeout=15.0, max_uploads=32, per_ip=8):
        self.app = app
        self.idle_timeout = idle_timeout
        self.total_timeout = total_timeout
        self.max_uploads = max_uploads
        self.per_ip = per_ip
        self.uploads = 0
        self.clients = {}

    async def __call__(self,scope,receive,send):
        if scope['type']!='http': return await self.app(scope,receive,send)
        language = Request(scope).headers.get('accept-language', '')
        has_body = any(k.lower() == b'transfer-encoding' or
                       (k.lower() == b'content-length' and v.strip() != b'0') for k, v in scope['headers'])
        client = (scope.get('client') or ('unknown', 0))[0]
        if has_body:
            # One event loop owns this middleware; no await occurs before admission.
            if self.clients.get(client, 0) >= self.per_ip or self.uploads >= self.max_uploads:
                return await error_response('Too many uploads in progress.', 429, language=language,
                                            headers={'Connection': 'close', 'Retry-After': '1'})(scope,receive,send)
            self.uploads += 1
            self.clients[client] = self.clients.get(client, 0) + 1
        total=0; chunks=[]
        try:
            with anyio.fail_after(self.total_timeout):
                while True:
                    with anyio.fail_after(self.idle_timeout):
                        message=await receive()
                    if message['type']=='http.disconnect': return
                    body=message.get('body',b'');total+=len(body)
                    if total>131072:
                        return await error_response('Request is too large.', 413, language=language,
                                                    headers={'Connection': 'close'})(scope,receive,send)
                    if body: chunks.append(body)
                    if not message.get('more_body',False): break
        except TimeoutError:
            return await error_response('Request upload timed out.', 408, language=language,
                                        headers={'Connection': 'close'})(scope,receive,send)
        finally:
            if has_body:
                self.uploads -= 1
                remaining = self.clients[client] - 1
                if remaining: self.clients[client] = remaining
                else: del self.clients[client]
        delivered=False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered=True
                return {'type':'http.request','body':b''.join(chunks),'more_body':False}
            return await receive()
        await self.app(scope,bounded_receive,send)


def require_permission(user, permission):
    if permission not in ROLE_PERMISSIONS.get(user['role'], ()):
        fail('You do not have permission to perform this action.', 403)


def audit(db, actor, action, target, detail, now):
    db.execute('INSERT INTO audit_log(actor_id,action,target_id,detail,created) VALUES(?,?,?,?,?)',
               (actor, action, target, json.dumps(detail, ensure_ascii=False), now))


def protect_last_admin(db, user):
    if user['role'] == 'admin' and not user['suspended']:
        count = db.execute("SELECT count(*) FROM users WHERE role='admin' AND suspended=0").fetchone()[0]
        if count <= 1:
            fail('The last active admin cannot be removed or suspended.', 409)


def set_role(db, user, role, actor, reason, now):
    if role not in ROLE_PERMISSIONS:
        fail('Invalid role.')
    if user['role'] == role:
        return
    if role != 'admin':
        protect_last_admin(db, user)
    db.execute('UPDATE users SET role=? WHERE id=?', (role, user['id']))
    audit(db, actor, 'user.role', user['id'], {'from': user['role'], 'to': role, 'reason': reason}, now)


def set_suspended(db, user, suspended, actor, reason, now):
    if bool(user['suspended']) == suspended:
        return
    uid = user['id']
    if suspended:
        protect_last_admin(db, user)
    db.execute('UPDATE users SET suspended=? WHERE id=?', (int(suspended), uid))
    if suspended:
        db.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
        db.execute('DELETE FROM invitations WHERE sender_id=? OR recipient_id=?', (uid, uid))
        db.execute('UPDATE connections SET ended=? WHERE ended IS NULL AND (first_id=? OR second_id=?)', (now, uid, uid))
    audit(db, actor, 'user.suspend' if suspended else 'user.restore', uid, {'reason': reason}, now)


def verify_age(db, user, birth, actor, reason, now):
    birth = validate_birth(birth, now)
    uid = user['id']
    db.execute('UPDATE users SET birth_date=?,age_verified=1 WHERE id=?', (birth, uid))
    if user['birth_date'] != birth:
        db.execute('UPDATE connections SET ended=? WHERE ended IS NULL AND (first_id=? OR second_id=?)', (now, uid, uid))
        db.execute('DELETE FROM invitations WHERE sender_id=? OR recipient_id=?', (uid, uid))
    # Birth dates and credentials never enter the audit detail.
    audit(db, actor, 'user.verify_age', uid, {'birthDateCorrected': user['birth_date'] != birth, 'reason': reason}, now)


def review_report(db, rid, status, note, actor, now):
    if status not in ('open', 'reviewed', 'dismissed'):
        fail('Invalid report status.')
    if not db.execute('SELECT 1 FROM reports WHERE id=?', (rid,)).fetchone():
        fail('Report not found.', 404)
    db.execute('UPDATE reports SET status=?,review_note=?,reviewer_id=?,reviewed_at=? WHERE id=?',
               (status, note, actor, now, rid))
    audit(db, actor, 'report.review', rid, {'status': status, 'note': note}, now)


def apply_staff_action(db, user, kind, p, now):
    permission = STAFF_ACTIONS.get(kind)
    if permission is None:
        fail('Invalid staff action.')
    require_permission(user, permission)
    allowed = {
        'staff.report.review': {'id', 'status', 'reason'},
        'staff.report.hide': {'id', 'reason'},
        'staff.report.restore': {'id', 'reason'},
        'staff.user.suspend': {'userID', 'suspended', 'reason'},
        'staff.user.verify_age': {'userID', 'birthDate', 'reason'},
        'staff.user.role': {'userID', 'role', 'reason'},
    }[kind]
    if set(p) - allowed:
        fail('Invalid field in staff action.')
    reason = text_field(p, 'reason', 1000)
    if kind == 'staff.report.review':
        review_report(db, identifier(p.get('id')), p.get('status'), reason, user['id'], now)
    elif kind in ('staff.report.hide', 'staff.report.restore'):
        rid = identifier(p.get('id'))
        row = db.execute('''SELECT j.* FROM reports r JOIN journals j ON j.id=r.journal_id
                            WHERE r.id=? AND j.author_id=r.reported_id''', (rid,)).fetchone()
        if row is None:
            fail('The post has been deleted.', 409)
        held = db.execute('SELECT 1 FROM moderation_holds WHERE journal_id=?', (row['id'],)).fetchone()
        if kind == 'staff.report.restore':
            if not held: fail('This entry has no sharing restriction.', 409)
            db.execute('DELETE FROM moderation_holds WHERE journal_id=?', (row['id'],))
            review_report(db, rid, 'reviewed', reason, user['id'], now)
            audit(db, user['id'], 'report.restore', rid, {'journalID': row['id'], 'reason': reason}, now)
            return {}
        if held or row['audience'] != 'community':
            fail('The community post is hidden or no longer public.', 409)
        db.execute('INSERT INTO moderation_holds VALUES(?,?,?)', (row['id'], user['id'], now))
        # The owner's private body survives. Only the reported public post is withdrawn.
        db.execute("UPDATE journals SET audience='privateOnly',shared_text='',connection_id=NULL WHERE id=?", (row['id'],))
        db.execute('DELETE FROM comments WHERE journal_id=?', (row['id'],))
        db.execute('DELETE FROM listening WHERE journal_id=?', (row['id'],))
        review_report(db, rid, 'reviewed', reason, user['id'], now)
        audit(db, user['id'], 'report.hide', rid, {'journalID': row['id'], 'reason': reason}, now)
    else:
        target = db.execute('SELECT * FROM users WHERE id=?', (identifier(p.get('userID')),)).fetchone()
        if target is None:
            fail('Account not found.', 404)
        if target['id'] == user['id'] or target['role'] == 'admin':
            fail('Use a backend server command to change an admin account.', 403)
        if kind == 'staff.user.role':
            if p.get('role') not in ('user', 'moderator'):
                fail('Admin access can only be granted with a backend server command.', 403)
            set_role(db, target, p['role'], user['id'], reason, now)
        elif kind == 'staff.user.suspend':
            if 'suspended' not in p:
                fail('The suspended field is required.')
            set_suspended(db, target, bool_field(p, 'suspended'), user['id'], reason, now)
        else:
            verify_age(db, target, text_field(p, 'birthDate', 10), user['id'], reason, now)
    return {}


def staff_report_dto(db, row):
    journal = db.execute("""SELECT 1 FROM journals j WHERE id=? AND author_id=? AND audience='community'
                            AND NOT EXISTS(SELECT 1 FROM moderation_holds h WHERE h.journal_id=j.id)""",
                         (row['journal_id'], row['reported_id'])).fetchone()
    names = {r['id']: r['nickname'] for r in db.execute('SELECT id,nickname FROM users WHERE id IN (?,?)',
                                                       (row['reporter_id'], row['reported_id']))}
    return dict(id=row['id'], reporterID=row['reporter_id'], reportedID=row['reported_id'],
                reporterNickname=names[row['reporter_id']], reportedNickname=names[row['reported_id']],
                reason=row['reason'], status=row['status'], date=row['created']-SWIFT_EPOCH,
                journalID=row['journal_id'], evidence=row['evidence'], canHide=bool(journal),
                canRestore=bool(db.execute('SELECT 1 FROM moderation_holds WHERE journal_id=?', (row['journal_id'],)).fetchone()),
                reviewNote=row['review_note'], reviewerID=row['reviewer_id'],
                reviewedAt=row['reviewed_at']-SWIFT_EPOCH if row['reviewed_at'] is not None else None)


def apply_action(db,user,kind,p,now):
    uid=user['id']
    if kind.startswith('staff.'):
        return apply_staff_action(db, user, kind, p, now)
    if kind=='journal.save':
        jid=identifier(p.get('id')) if p.get('id') else new_id()
        old=db.execute('SELECT * FROM journals WHERE id=?',(jid,)).fetchone()
        if old and old['author_id']!=uid: fail('You cannot edit this post.',403)
        if p.get('id') and old is None: fail('The journal entry to edit could not be found.',404)
        body=text_field(p,'body',20000); title=text_field(p,'title',160,default='',empty=True)
        audience=p.get('audience','privateOnly')
        if audience not in ('privateOnly','companion','community'): fail('Invalid sharing option.')
        if audience != 'privateOnly' and db.execute('SELECT 1 FROM moderation_holds WHERE journal_id=?', (jid,)).fetchone():
            fail('Sharing is restricted for this entry. You can still save privately; contact staff for a review.', 403)
        excerpt=text_field(p,'sharedText',20000,default='',empty=True)
        if audience!='privateOnly' and (not excerpt or excerpt not in body): fail('The shared passage must be part of your journal entry.')
        support=support_field(p)
        conn=active(db,uid) if audience=='companion' else None
        if audience=='companion' and conn is None: fail('You don’t have a connection yet.')
        if conn and not eligible(db,conn['first_id'],conn['second_id'],now): fail('The age groups for this connection need to be reviewed.',403)
        values=(jid,uid,title,body,excerpt if audience!='privateOnly' else '',audience,conn['id'] if conn else None,
                int(bool_field(p,'anonymous')),int(bool_field(p,'commentsEnabled',True)),support,old['created'] if old else now)
        db.execute('''INSERT INTO journals VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
          title=excluded.title,body=excluded.body,shared_text=excluded.shared_text,audience=excluded.audience,
          connection_id=excluded.connection_id,anonymous=excluded.anonymous,comments_enabled=excluded.comments_enabled,support=excluded.support''',values)
        if audience!='community':
            db.execute('DELETE FROM comments WHERE journal_id=?',(jid,))
            db.execute('DELETE FROM listening WHERE journal_id=?',(jid,))
        if bool_field(p, 'anonymous'):
            db.execute('DELETE FROM invitations WHERE source_journal_id=?', (jid,))
        return {'id':jid}
    if kind=='journal.hide':
        row=get_journal(db,p.get('id'),uid)
        if row['audience'] != 'community' or row['author_id'] == uid:
            fail('You can only hide another person’s community post.', 400)
        db.execute('INSERT OR IGNORE INTO hidden_posts VALUES(?,?)', (uid, row['id']))
        return {}
    if kind=='journal.delete':
        row=get_journal(db,p.get('id'),uid)
        if row['author_id']!=uid: fail('You cannot delete this post.',403)
        db.execute('DELETE FROM journals WHERE id=?',(row['id'],)); return {}
    if kind in ('journal.listen','journal.comment'):
        row=get_journal(db,p.get('id'),uid)
        if row['audience']!='community': fail('This post is private.',403)
        if kind=='journal.listen':
            if row['author_id']==uid: fail('You cannot react to your own post.')
            enabled=bool_field(p,'enabled',True)
            if enabled: db.execute('INSERT OR IGNORE INTO listening VALUES(?,?)',(row['id'],uid))
            else: db.execute('DELETE FROM listening WHERE journal_id=? AND user_id=?',(row['id'],uid))
        else:
            if not row['comments_enabled']: fail('Responses are turned off for this post.',403)
            db.execute('INSERT INTO comments VALUES(?,?,?,?,?)',(new_id(),row['id'],uid,text_field(p,'text',2000),now))
        return {}
    if kind=='invitation.send':
        source=None
        if p.get('journalID'):
            source=get_journal(db,p['journalID'],uid)
            if source['anonymous']:
                fail('Anonymous stories do not accept invitations. Connect through a shared profile.', 403)
            if source['audience']!='community': fail('This post does not accept invitations.',403)
            target=source['author_id']
        else: target=identifier(p.get('userID'))
        if not can_invite(db,uid,target,now): fail('Both people need verified ages, compatible age groups, and no current connection.',403)
        if db.execute('SELECT 1 FROM invitations WHERE (sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?)',(uid,target,target,uid)).fetchone(): fail('An invitation already exists between you.',409)
        if db.execute('SELECT count(*) FROM invitations WHERE sender_id=?',(uid,)).fetchone()[0]>=20: fail('You can have up to 20 pending invitations.',409)
        iid=new_id();db.execute('INSERT INTO invitations VALUES(?,?,?,?,?,?)',(iid,uid,target,source['id'] if source else None,source['id'] if source and source['anonymous'] else None,now));return {'id':iid}
    if kind in ('invitation.accept','invitation.dismiss'):
        row=db.execute('SELECT * FROM invitations WHERE id=?',(identifier(p.get('id')),)).fetchone()
        if row is None or uid not in (row['sender_id'],row['recipient_id']): fail('This invitation could not be found.',404)
        if kind=='invitation.accept':
            if row['recipient_id']!=uid: fail('Only the recipient can accept an invitation.',403)
            a,b=row['sender_id'],row['recipient_id']
            if not can_invite(db,a,b,now): fail('This connection is no longer eligible, or someone has another connection.',409)
            cid=new_id();db.execute('INSERT INTO connections(id,first_id,second_id,started) VALUES(?,?,?,?)',(cid,a,b,now))
            db.execute('DELETE FROM invitations WHERE sender_id IN (?,?) OR recipient_id IN (?,?)',(a,b,a,b))
            return {'id':cid}
        db.execute('DELETE FROM invitations WHERE id=?',(row['id'],));return {}
    if kind in ('message.send','connection.checkin','connection.pause','connection.leave'):
        conn=active(db,uid)
        if conn is None or conn['id']!=identifier(p.get('connectionID')): fail('This connection is no longer active.',409)
        cid=conn['id']
        if kind!='connection.leave' and not eligible(db,conn['first_id'],conn['second_id'],now): fail('The age groups for this connection need to be reviewed.',403)
        if kind=='message.send':
            mid=new_id();db.execute('INSERT INTO messages VALUES(?,?,?,?,?)',(mid,cid,uid,text_field(p,'text',4000),now));return {'id':mid}
        if kind=='connection.leave': db.execute('UPDATE connections SET ended=? WHERE id=?',(now,cid))
        if kind=='connection.pause': db.execute('UPDATE connections SET paused=? WHERE id=?',(int(bool_field(p,'paused')),cid))
        if kind=='connection.checkin':
            if conn['paused']: fail('The garden is resting.',409)
            today=datetime.fromtimestamp(now,timezone.utc).date();key=today.isoformat()
            db.execute('INSERT OR IGNORE INTO checkins VALUES(?,?,?)',(cid,uid,key))
            count=db.execute('SELECT count(*) FROM checkins WHERE connection_id=? AND day=?',(cid,key)).fetchone()[0]
            if count==2 and conn['last_complete_day']!=key:
                streak=conn['streak']+1 if conn['last_complete_day']==(today-timedelta(days=1)).isoformat() else 1
                db.execute('UPDATE connections SET total_days=total_days+1,streak=?,best_streak=max(best_streak,?),last_complete_day=? WHERE id=?',(streak,streak,key,cid))
        return {}
    if kind in ('user.block','report.create'):
        source = None
        if p.get('journalID'):
            source=get_journal(db,p['journalID'],uid)
            target=source['author_id']
            if kind=='user.block' and source['anonymous'] and source['audience']=='community':
                # Compatibility for old clients: hide this story without a named-account side effect.
                if target==uid: fail('You cannot hide your own post.')
                db.execute('INSERT OR IGNORE INTO hidden_posts VALUES(?,?)', (uid, source['id']))
                return {}
        else: target=identifier(p.get('userID'))
        if target==uid or db.execute('SELECT 1 FROM users WHERE id=?',(target,)).fetchone() is None: fail('Invalid user.')
        if kind=='user.block':
            db.execute('INSERT OR IGNORE INTO blocks VALUES(?,?)',(uid,target))
            db.execute('DELETE FROM invitations WHERE (sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?)',(uid,target,target,uid))
            db.execute('UPDATE connections SET ended=? WHERE ended IS NULL AND ((first_id=? AND second_id=?) OR (first_id=? AND second_id=?))',(now,uid,target,target,uid))
        else:
            # Preserve only the excerpt explicitly published to the community, never a private body/chat.
            public = source is not None and source['audience'] == 'community'
            db.execute('INSERT INTO reports(id,reporter_id,reported_id,reason,created,journal_id,evidence) VALUES(?,?,?,?,?,?,?)',
                       (new_id(),uid,target,text_field(p,'reason',1000),now,source['id'] if public else None,source['shared_text'] if public else ''))
        return {}
    if kind=='profile.update':
        nickname=text_field(p,'nickname',40); bio=text_field(p,'bio',500,default='',empty=True)
        interests=p.get('interests',[])
        if not isinstance(interests,list) or len(interests)>8 or any(not isinstance(x,str) or not 1<=len(x.strip())<=30 for x in interests): fail('Choose up to 8 interests, each between 1 and 30 characters.')
        support=support_field(p)
        pace=text_field(p,'pace',80,default='Evenings')
        db.execute('UPDATE users SET nickname=?,bio=?,interests=?,support=?,pace=? WHERE id=?',(nickname,bio,json.dumps([x.strip() for x in interests],ensure_ascii=False),support,pace,uid));return {}
    fail('This action is not supported.')


def create_app(path: str | Path = 'data/dearly.sqlite3', *, clock: Callable[[],float] = time.time,
               body_idle_timeout: float = 5.0, body_total_timeout: float = 15.0,
               web_dir: str | Path | None = None) -> FastAPI:
    if body_idle_timeout <= 0 or body_total_timeout <= 0:
        raise ValueError('Request body timeouts must be positive.')
    database=Database(path); limiter=Limiter(); hashing=threading.BoundedSemaphore(2); hub=ChatHub()
    @asynccontextmanager
    async def lifespan(app):
        anyio.to_thread.current_default_thread_limiter().total_tokens=16
        yield
    app=FastAPI(title='Dearly API',version='0.5.0',docs_url='/docs',redoc_url=None,lifespan=lifespan)
    app.state.database=database
    app.add_middleware(BodyLimit, idle_timeout=body_idle_timeout, total_timeout=body_total_timeout)
    app.add_middleware(BrowserSession)

    @app.exception_handler(RequestError)
    async def request_error(request, exc):
        return error_response(exc.message, exc.status_code, language=request.headers.get('accept-language', ''),
                              **exc.parameters)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        # Do not reflect submitted credentials back in validation responses.
        return error_response('Invalid details. Check your username, password, and required fields.', 422,
                              language=request.headers.get('accept-language', ''))

    @app.exception_handler(sqlite3.OperationalError)
    async def database_busy(request,exc):
        return error_response('The database is busy. Please try again.', 503,
                              language=request.headers.get('accept-language', ''), headers={'Retry-After':'1'})

    def authenticate(db,authorization):
        if not authorization or not authorization.startswith('Bearer ') or len(authorization)>512: fail('Please log in.',401)
        digest=hashlib.sha256(authorization[7:].encode()).hexdigest()
        user=db.execute('SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires>? AND u.suspended=0',(digest,clock())).fetchone()
        if user is None: fail('Your session has expired or your account is locked. Please log in again.',401)
        return user

    def auth_rate(request,username):
        ip=request.client.host if request.client else 'unknown'
        limiter.check('auth-ip:'+ip,12,1/10)
        limiter.check('auth-user:'+username.lower(),8,1/15)

    def session(db,uid):
        token=secrets.token_urlsafe(32);expires=clock()+30*86400
        db.execute('DELETE FROM sessions WHERE expires<?',(clock(),))
        # At most 8 sessions per account; drop oldest when adding the ninth.
        db.execute('DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM sessions WHERE user_id=? ORDER BY expires DESC LIMIT -1 OFFSET 7)',(uid,))
        db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,expires))
        return dict(token=token,userID=uid,expiresAt=expires-SWIFT_EPOCH)

    @app.get('/health')
    def health(): return {'status':'ok','version':'0.5.0','dayBoundary':'UTC'}

    @app.post('/v1/auth/register',status_code=201)
    def register(data: Registration,request: Request):
        auth_rate(request,data.username)
        birth=validate_birth(data.birthDate,clock());nickname=data.nickname.strip()
        if not nickname: fail('Please enter a nickname.')
        if not hashing.acquire(blocking=False): fail('Sign-in is busy. Please try again shortly.',429)
        try: encoded=password_hash(data.password)
        finally: hashing.release()
        with database.connect(write=True) as db:
            if db.execute('SELECT 1 FROM users WHERE username=?',(data.username.lower(),)).fetchone(): fail('This username is already taken.',409)
            uid=new_id()
            # Explicit defaults also apply to databases whose original column defaults were Vietnamese.
            db.execute('INSERT INTO users(id,username,password_hash,nickname,birth_date,created,interests,support,pace) VALUES(?,?,?,?,?,?,?,?,?)',
                       (uid,data.username.lower(),encoded,nickname,birth,clock(),json.dumps(['Music','Reading']),'listen','Evenings'))
            changed(db);return browser_session(session(db,uid), request, 201)

    @app.post('/v1/auth/login')
    def login(data: Credentials,request: Request):
        auth_rate(request,data.username)
        with database.connect() as db:
            user=db.execute('SELECT * FROM users WHERE username=?',(data.username.lower(),)).fetchone()
        # Fixed-cost dummy verification avoids a fast nonexistent-username path.
        dummy='pbkdf2-sha256$600000$'+'00'*16+'$'+'00'*32
        if not hashing.acquire(blocking=False): fail('Sign-in is busy. Please try again shortly.',429)
        try: valid=password_matches(data.password,user['password_hash'] if user else dummy)
        finally: hashing.release()
        if not valid or user is None or user['suspended']: fail('Incorrect username or password.',401)
        with database.connect(write=True) as db:
            if db.execute('SELECT suspended FROM users WHERE id=?',(user['id'],)).fetchone()[0]: fail('This account is unavailable.',401)
            return browser_session(session(db,user['id']), request)

    @app.post('/v1/auth/logout')
    def logout(authorization: str | None=Header(default=None)):
        with database.connect(write=True) as db:
            authenticate(db,authorization)
            db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(authorization[7:].encode()).hexdigest(),))
        hub.publish()
        response=JSONResponse({'ok':True},headers={'Cache-Control':'no-store'})
        response.delete_cookie(COOKIE,path='/')
        return response

    @app.get('/v1/state')
    def state(authorization: str | None=Header(default=None),if_none_match: str | None=Header(default=None)):
        with database.connect() as db:
            user=authenticate(db,authorization);now=clock()
            limiter.check('read:'+user['id'],60,1)
            revision=db.execute('SELECT revision FROM meta WHERE id=1').fetchone()[0]
            day=datetime.fromtimestamp(now,timezone.utc).date().isoformat()
            tag='"'+hashlib.sha256(f'{user["id"]}:{revision}:{day}'.encode()).hexdigest()+'"'
            headers={'ETag':tag,'Cache-Control':'no-store','Vary':'Authorization'}
            if if_none_match==tag: return Response(status_code=304,headers=headers)
            return JSONResponse(dict(state=snapshot(db,user,now),serverNow=now-SWIFT_EPOCH),headers=headers)

    def execute_action(data: Action, authorization):
        rid=identifier(data.requestID)
        fingerprint=hashlib.sha256(json.dumps({'kind':data.kind,'payload':data.payload},sort_keys=True,separators=(',',':')).encode()).hexdigest()
        with database.connect(write=True) as db:
            user=authenticate(db,authorization);uid=user['id'];now=clock()
            limiter.check('write:'+uid,40,1)
            # Re-check permissions even on an idempotent retry after demotion.
            if data.kind.startswith('staff.'):
                require_permission(user, STAFF_ACTIONS.get(data.kind, 'unknown'))
            previous=db.execute('SELECT * FROM requests WHERE user_id=? AND request_id=?',(uid,rid)).fetchone()
            if previous:
                if previous['payload_hash']!=fingerprint: fail('This request ID was already used for different content.',409)
                return json.loads(previous['result'])
            result={'ok':True,**apply_action(db,user,data.kind,data.payload,now)}
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?)',(uid,rid,fingerprint,json.dumps(result),now))
            db.execute('DELETE FROM requests WHERE created<?',(now-7*86400,))
            changed(db)
        if data.kind=='message.send':
            hub.publish({'type':'message', 'id':result['id'], 'connectionID':identifier(data.payload['connectionID'])})
        else:
            hub.publish()
        return result

    @app.post('/v1/actions')
    def action(data: Action,authorization: str | None=Header(default=None)):
        return execute_action(data,authorization)

    def socket_user(authorization, event=None):
        with database.connect() as db:
            user=authenticate(db,authorization)
            message=None
            if event and event['type']=='message':
                conn=active(db,user['id'])
                if conn and conn['id']==event['connectionID'] and eligible(db,conn['first_id'],conn['second_id'],clock()):
                    row=db.execute('SELECT * FROM messages WHERE id=? AND connection_id=?',
                                   (event['id'],conn['id'])).fetchone()
                    if row: message=message_dto(row)
            return user['id'],message

    @app.websocket('/ws/chat')
    async def chat(websocket: WebSocket):
        # Browser cookies are never accepted across origins; native clients authenticate in-frame.
        if not same_origin(websocket) or (websocket.cookies.get(COOKIE) and not websocket.headers.get('origin')):
            await websocket.close(code=4403);return
        try:
            ip=websocket.client.host if websocket.client else 'unknown'
            limiter.check('socket-ip:'+ip,12,1/10)
        except RequestError:
            await websocket.close(code=4429);return
        await websocket.accept()
        tasks=[]
        try:
            raw=await asyncio.wait_for(websocket.receive_text(),timeout=5)
            if len(raw.encode())>16384: await websocket.close(code=1009);return
            frame=json.loads(raw)
            if not isinstance(frame,dict) or frame.get('type')!='authenticate':
                await websocket.close(code=4401);return
            token=websocket.cookies.get(COOKIE) or frame.get('token')
            if not isinstance(token,str) or len(token)>128:
                await websocket.close(code=4401);return
            authorization='Bearer '+token
            uid,_=await anyio.to_thread.run_sync(socket_user,authorization)
            with hub.subscribe(uid) as queue:
                await websocket.send_json({'type':'ready','userID':uid})
                incoming=asyncio.create_task(websocket.receive_text())
                outgoing=asyncio.create_task(queue.get())
                tasks=[incoming,outgoing]
                while True:
                    done,_=await asyncio.wait(tasks,timeout=15,return_when=asyncio.FIRST_COMPLETED)
                    # Re-check revocation and suspension even on an idle socket / CLI changes.
                    await anyio.to_thread.run_sync(socket_user,authorization)
                    if not done:
                        await websocket.send_json({'type':'ping'});continue
                    if incoming in done:
                        raw=incoming.result()
                        if len(raw.encode())>16384: await websocket.close(code=1009);return
                        frame=json.loads(raw)
                        request_id=frame.get('requestID') if isinstance(frame,dict) else None
                        try:
                            limiter.check('socket-frame:'+uid,60,2)
                            if not isinstance(frame,dict): fail('Invalid chat frame.')
                            if frame.get('type')=='ping':
                                await websocket.send_json({'type':'pong'})
                            elif frame.get('type')=='message.send':
                                command=Action.model_validate({'requestID':request_id,'kind':'message.send',
                                    'payload':{'connectionID':frame.get('connectionID'),'text':frame.get('text')}})
                                result=await anyio.to_thread.run_sync(execute_action,command,authorization)
                                await websocket.send_json({'type':'ack','requestID':request_id,'result':result})
                            else: fail('This chat frame is not supported.')
                        except (RequestError,ValidationError) as exc:
                            status=exc.status_code if isinstance(exc,RequestError) else 400
                            detail=str(exc.detail) if isinstance(exc,RequestError) else 'Invalid chat message.'
                            await websocket.send_json({'type':'error','requestID':request_id,'status':status,'detail':detail})
                            if status==429: await websocket.close(code=4429);return
                        incoming=asyncio.create_task(websocket.receive_text())
                        tasks=[incoming,outgoing]
                    if outgoing in done:
                        event=outgoing.result()
                        _,message=await anyio.to_thread.run_sync(socket_user,authorization,event)
                        if message: await websocket.send_json({'type':'message','message':message})
                        elif event['type']=='state.changed': await websocket.send_json(event)
                        outgoing=asyncio.create_task(queue.get())
                    tasks=[incoming,outgoing]
        except RequestError as exc:
            await websocket.close(code=4401 if exc.status_code==401 else 4403)
        except OverflowError:
            await websocket.close(code=4429)
        except (asyncio.TimeoutError, json.JSONDecodeError, UnicodeError, KeyError, TypeError):
            await websocket.close(code=1008)
        except sqlite3.OperationalError:
            await websocket.close(code=1013)
        except WebSocketDisconnect:
            pass
        except asyncio.CancelledError:
            pass
        finally:
            for task in tasks: task.cancel()
            with anyio.CancelScope(shield=True):
                if tasks: await asyncio.gather(*tasks,return_exceptions=True)

    staff_headers = {'Cache-Control': 'no-store', 'Vary': 'Authorization'}

    @app.get('/v1/staff/reports')
    def staff_reports(status: str='open', before: str | None=None, limit: int=30,
                      authorization: str | None=Header(default=None)):
        if status not in ('open', 'reviewed', 'dismissed') or not 1 <= limit <= 50:
            fail('Invalid report filter.')
        with database.connect() as db:
            user = authenticate(db, authorization)
            require_permission(user, 'reports.read')
            limiter.check('read:'+user['id'], 60, 1)
            where = 'status=?'; args = [status]
            if before:
                cursor = db.execute('SELECT created,id FROM reports WHERE id=?', (identifier(before),)).fetchone()
                if cursor is None: fail('Invalid page cursor.')
                where += ' AND (created,id)<(?,?)'; args.extend([cursor['created'], cursor['id']])
            rows = db.execute(f'SELECT * FROM reports WHERE {where} ORDER BY created DESC,id DESC LIMIT ?', (*args, limit+1)).fetchall()
            page = rows[:limit]
            return JSONResponse(dict(items=[staff_report_dto(db, r) for r in page],
                                     nextCursor=page[-1]['id'] if len(rows)>limit else None), headers=staff_headers)

    @app.get('/v1/staff/users')
    def staff_users(q: str='', before: str | None=None, limit: int=30,
                    authorization: str | None=Header(default=None)):
        if not 1 <= limit <= 50 or len(q)>80: fail('Invalid account filter.')
        with database.connect() as db:
            user = authenticate(db, authorization)
            require_permission(user, 'users.read')
            limiter.check('read:'+user['id'], 60, 1)
            query = q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            where = "(username LIKE ? ESCAPE '\\' OR nickname LIKE ? ESCAPE '\\')"; args = [query, query]
            if before:
                cursor = db.execute('SELECT created,id FROM users WHERE id=?', (identifier(before),)).fetchone()
                if cursor is None: fail('Invalid page cursor.')
                where += ' AND (created,id)<(?,?)'; args.extend([cursor['created'], cursor['id']])
            rows = db.execute(f'''SELECT id,username,nickname,role,suspended,age_verified,birth_date,created
                                 FROM users WHERE {where} ORDER BY created DESC,id DESC LIMIT ?''', (*args, limit+1)).fetchall()
            page = rows[:limit]
            items = [dict(id=r['id'], username=r['username'], nickname=r['nickname'], role=r['role'],
                          suspended=bool(r['suspended']), ageVerified=bool(r['age_verified']), birthDate=r['birth_date']) for r in page]
            return JSONResponse(dict(items=items, nextCursor=page[-1]['id'] if len(rows)>limit else None), headers=staff_headers)

    @app.get('/v1/staff/audit')
    def staff_audit(before: int | None=None, limit: int=30, authorization: str | None=Header(default=None)):
        if not 1 <= limit <= 50 or (before is not None and before < 1): fail('Invalid page cursor.')
        with database.connect() as db:
            user = authenticate(db, authorization)
            require_permission(user, 'audit.read')
            limiter.check('read:'+user['id'], 60, 1)
            rows = db.execute('''SELECT a.*,u.nickname AS actor_name FROM audit_log a LEFT JOIN users u ON u.id=a.actor_id
                                 WHERE (? IS NULL OR a.id<?) ORDER BY a.id DESC LIMIT ?''', (before, before, limit+1)).fetchall()
            page = rows[:limit]
            items = [dict(id=r['id'], actorID=r['actor_id'], actorName=r['actor_name'] or 'Server CLI', action=r['action'],
                          targetID=r['target_id'], detail=json.loads(r['detail']), date=r['created']-SWIFT_EPOCH) for r in page]
            return JSONResponse(dict(items=items, nextCursor=page[-1]['id'] if len(rows)>limit else None), headers=staff_headers)

    @app.get('/v1/journals')
    def own_journals(before: str | None=None,limit: int=40,authorization: str | None=Header(default=None)):
        if not 1<=limit<=60: fail('The limit must be between 1 and 60.')
        with database.connect() as db:
            user=authenticate(db,authorization);uid=user['id'];now=clock()
            limiter.check('read:'+uid,60,1)
            args=[uid];where='author_id=?'
            if before:
                cursor=db.execute('SELECT created,id FROM journals WHERE id=? AND author_id=?',(identifier(before),uid)).fetchone()
                if cursor is None: fail('Invalid page cursor.')
                where+=' AND (created,id)<(?,?)';args.extend([cursor['created'],cursor['id']])
            rows=db.execute(f'SELECT * FROM journals WHERE {where} ORDER BY created DESC,id DESC LIMIT ?',(*args,limit+1)).fetchall()
            page=rows[:limit]
            return JSONResponse(dict(items=[journal_dto(db,r,uid,now) for r in page],
                                     nextCursor=page[-1]['id'] if len(rows)>limit else None), headers=staff_headers)

    @app.get('/v1/connections')
    def archived_connections(before: str | None=None, limit: int=20, authorization: str | None=Header(default=None)):
        if not 1 <= limit <= 50: fail('limit must be between 1 and 50.')
        with database.connect() as db:
            user=authenticate(db,authorization);uid=user['id'];now=clock()
            limiter.check('read:'+uid,60,1)
            where='ended IS NOT NULL AND (first_id=? OR second_id=?)';args=[uid,uid]
            if before:
                cursor=db.execute('''SELECT started,id FROM connections WHERE id=? AND ended IS NOT NULL
                                     AND (first_id=? OR second_id=?)''', (identifier(before),uid,uid)).fetchone()
                if cursor is None: fail('Invalid page cursor.')
                where+=' AND (started,id)<(?,?)';args.extend([cursor['started'],cursor['id']])
            rows=db.execute(f'SELECT * FROM connections WHERE {where} ORDER BY started DESC,id DESC LIMIT ?',
                            (*args,limit+1)).fetchall()
            page=rows[:limit]
            profile_ids={uid}
            for row in page: profile_ids.update((row['first_id'],row['second_id']))
            marks=','.join('?' for _ in profile_ids)
            profiles=[profile_dto(r,now) for r in db.execute(f'SELECT * FROM users WHERE id IN ({marks})',list(profile_ids))]
            return JSONResponse(dict(items=[connection_dto(db,r,now) for r in page], profiles=profiles,
                                     nextCursor=page[-1]['id'] if len(rows)>limit else None), headers=staff_headers)

    @app.get('/v1/messages')
    def history(connectionID: str,before: str | None=None,limit: int=50,authorization: str | None=Header(default=None)):
        if not 1<=limit<=100: fail('The limit must be between 1 and 100.')
        with database.connect() as db:
            user=authenticate(db,authorization);conn=active(db,user['id'])
            if conn is None or conn['id']!=identifier(connectionID): fail('You do not have permission to read this chat.',403)
            limiter.check('read:'+user['id'],60,1)
            args=[conn['id']];where='connection_id=?'
            if before:
                cursor=db.execute('SELECT created,id FROM messages WHERE id=? AND connection_id=?',(identifier(before),conn['id'])).fetchone()
                if cursor is None: fail('Invalid page cursor.')
                where+=' AND (created,id)<(?,?)';args.extend([cursor['created'],cursor['id']])
            rows=db.execute(f'SELECT * FROM messages WHERE {where} ORDER BY created DESC,id DESC LIMIT ?',(*args,limit+1)).fetchall()
            page=rows[:limit]
            return JSONResponse(dict(items=[message_dto(r) for r in reversed(page)],
                                     nextCursor=page[-1]['id'] if len(rows)>limit else None), headers=staff_headers)

    selected_web=web_dir or os.environ.get('DEARLY_WEB_DIST')
    directory=Path(selected_web) if selected_web else Path(__file__).resolve().parents[1]/'web'/'dist'
    if (directory/'index.html').is_file():
        mount_web(app,directory)
    elif selected_web:
        raise ValueError('The selected web directory has no index.html. Run npm run build in web first.')
    return app
