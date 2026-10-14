"""Dearly single-node API. Python 3.11+, SQLite, standard asyncio on every OS."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
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

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
import anyio
from pydantic import BaseModel, ConfigDict, Field

SWIFT_EPOCH = 978307200  # Swift JSONEncoder default: seconds since 2001-01-01 UTC.
SUPPORT = {'Chỉ cần lắng nghe', 'Chia sẻ trải nghiệm', 'Cùng nghĩ cách'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL);
INSERT OR IGNORE INTO meta VALUES(1,0);
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 nickname TEXT NOT NULL, birth_date TEXT NOT NULL, age_verified INTEGER NOT NULL DEFAULT 0,
 symbol TEXT NOT NULL DEFAULT 'leaf.fill', bio TEXT NOT NULL DEFAULT '',
 interests TEXT NOT NULL DEFAULT '["Âm nhạc","Đọc sách"]',
 support TEXT NOT NULL DEFAULT 'Chỉ cần lắng nghe', pace TEXT NOT NULL DEFAULT 'Buổi tối',
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
PRAGMA user_version=1;
'''


def fail(message: str, status: int = 400):
    raise HTTPException(status, message)


def identifier(value) -> str:
    try:
        return str(uuid.UUID(str(value))).upper()
    except (ValueError, TypeError, AttributeError):
        fail('ID không hợp lệ.')


def new_id() -> str:
    return str(uuid.uuid4()).upper()


def text_field(payload: dict, key: str, maximum: int, *, default=None, empty=False) -> str:
    value = payload.get(key, default)
    if not isinstance(value, str):
        fail(f'Thiếu hoặc sai trường {key}.')
    value = value.strip()
    if (not value and not empty) or len(value) > maximum:
        fail(f'{key}: cần từ {0 if empty else 1} đến {maximum} ký tự.')
    return value


def bool_field(payload, key, default=False):
    value = payload.get(key, default)
    if not isinstance(value, bool):
        fail(f'{key} phải là true/false.')
    return value


def age_on(birth_date: str, today: date) -> int:
    born = date.fromisoformat(birth_date)
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def validate_birth(value: str, now: float) -> str:
    try:
        born = date.fromisoformat(value)
        age = age_on(born.isoformat(), datetime.fromtimestamp(now, timezone.utc).date())
    except (TypeError, ValueError):
        fail('Ngày sinh không hợp lệ.')
    if not 16 <= age <= 100:
        fail('Bản này hỗ trợ tài khoản từ 16 đến 100 tuổi.')
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
            if version not in (0, 1):
                raise RuntimeError('Unsupported database schema. Back up before upgrading.')
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)
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
    if blocked(db,uid,journal['author_id']):
        return False
    if journal['audience'] == 'community':
        return True
    if journal['audience'] == 'companion':
        connection = active(db,uid)
        return connection is not None and connection['id'] == journal['connection_id']
    return False


def get_journal(db, jid, uid):
    row = db.execute('SELECT * FROM journals WHERE id=?',(identifier(jid),)).fetchone()
    if row is None or not readable(db,row,uid):
        fail('Không tìm thấy bài viết.',404)
    return row


def profile_dto(row, now):
    return dict(id=row['id'], nickname=row['nickname'], age=age_on(row['birth_date'],datetime.fromtimestamp(now,timezone.utc).date()),
                ageVerified=bool(row['age_verified']), symbol=row['symbol'], bio=row['bio'], interests=json.loads(row['interests']), support=row['support'], pace=row['pace'])


def alias_profile(jid):
    return dict(id=jid,nickname='Một người bạn',age=0,ageVerified=False,symbol='sparkles',bio='',interests=[],support='Chỉ cần lắng nghe',pace='')


def journal_dto(db, row, uid, now):
    own = row['author_id'] == uid
    author = row['id'] if row['anonymous'] and not own else row['author_id']
    listening = db.execute('SELECT 1 FROM listening WHERE journal_id=? AND user_id=?',(row['id'],uid)).fetchone()
    return dict(id=row['id'],authorID=author,title=row['title'] if own else '',body=row['body'] if own else '',
                sharedText=row['shared_text'],audience=row['audience'],connectionID=row['connection_id'],anonymous=bool(row['anonymous']),
                commentsEnabled=bool(row['comments_enabled']),support=row['support'],date=row['created']-SWIFT_EPOCH,
                listeners=[uid] if listening else [],canInviteAuthor=can_invite(db,uid,row['author_id'],now))


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
       AND NOT EXISTS(SELECT 1 FROM blocks b WHERE (b.blocker_id=? AND b.blocked_id=j.author_id) OR (b.blocker_id=j.author_id AND b.blocked_id=?))
       ORDER BY j.created DESC,j.id DESC LIMIT ?''',(uid,uid,limit)).fetchall()
    conn=active(db,uid)
    shared=db.execute("SELECT * FROM journals WHERE connection_id=? AND audience='companion' ORDER BY created DESC,id DESC LIMIT ?",(conn['id'],limit)).fetchall() if conn else []
    journals={r['id']:r for r in own+feed+shared}
    journal_data=[]
    for row in journals.values():
        dto=journal_dto(db,row,uid,now); journal_data.append(dto)
        if dto['authorID'] != row['author_id']: aliases[dto['authorID']]=alias_profile(dto['authorID'])
        else: profile_ids.add(row['author_id'])
    connections=db.execute('SELECT * FROM connections WHERE first_id=? OR second_id=? ORDER BY started DESC LIMIT 20',(uid,uid)).fetchall()
    for c in connections: profile_ids.update([c['first_id'],c['second_id']])
    invitations=[]
    for row in db.execute('SELECT * FROM invitations WHERE sender_id=? OR recipient_id=? ORDER BY created DESC LIMIT 100',(uid,uid)):
        recipient=row['recipient_id']
        source=db.execute('SELECT * FROM journals WHERE id=?',(row['source_journal_id'],)).fetchone()
        if row['sender_id']==uid and (row['source_alias'] or (source and source['anonymous'])):
            recipient=row['source_alias'] or source['id']; aliases[recipient]=alias_profile(recipient)
        else: profile_ids.add(recipient)
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
        rows=db.execute(f'SELECT * FROM comments WHERE journal_id IN ({marks}) ORDER BY created DESC,id DESC LIMIT 200',public_ids).fetchall()
        for row in reversed(rows):
            if blocked(db,uid,row['author_id']): continue
            journal=journals[row['journal_id']]
            hide=journal['anonymous'] and row['author_id']==journal['author_id'] and uid!=row['author_id']
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
                blocks=[dict(blockerID=r['blocker_id'],blockedID=r['blocked_id']) for r in blockrows],reports=[],demoDayOffset=0,suggestedUserIDs=suggestion_ids)


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
                fail('Quá nhiều yêu cầu. Thử lại sau một chút.',429)
            self.items[key]=(tokens-1,now)
            while len(self.items)>4096: self.items.popitem(last=False)


class BodyLimit:
    """Enforce bounds on actual streamed bytes, not only Content-Length."""
    def __init__(self,app): self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http': return await self.app(scope,receive,send)
        total=0; chunks=[]
        while True:
            message=await receive()
            if message['type']=='http.disconnect': return
            body=message.get('body',b'');total+=len(body)
            if total>131072:
                return await JSONResponse({'detail':'Yêu cầu quá lớn.'},status_code=413)(scope,receive,send)
            chunks.append(body)
            if not message.get('more_body',False): break
        delivered=False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered=True
                return {'type':'http.request','body':b''.join(chunks),'more_body':False}
            return await receive()
        await self.app(scope,bounded_receive,send)


def apply_action(db,user,kind,p,now):
    uid=user['id']
    if kind=='journal.save':
        jid=identifier(p.get('id')) if p.get('id') else new_id()
        old=db.execute('SELECT * FROM journals WHERE id=?',(jid,)).fetchone()
        if old and old['author_id']!=uid: fail('Không thể sửa bài viết này.',403)
        if p.get('id') and old is None: fail('Không tìm thấy journal cần sửa.',404)
        body=text_field(p,'body',20000); title=text_field(p,'title',160,default='',empty=True)
        audience=p.get('audience','privateOnly')
        if audience not in ('privateOnly','companion','community'): fail('Chế độ chia sẻ không hợp lệ.')
        excerpt=text_field(p,'sharedText',20000,default='',empty=True)
        if audience!='privateOnly' and (not excerpt or excerpt not in body): fail('Đoạn chia sẻ phải nằm trong journal.')
        support=p.get('support','Chỉ cần lắng nghe')
        if support not in SUPPORT: fail('Lựa chọn phản hồi không hợp lệ.')
        conn=active(db,uid) if audience=='companion' else None
        if audience=='companion' and conn is None: fail('Bạn chưa có kết nối.')
        if conn and not eligible(db,conn['first_id'],conn['second_id'],now): fail('Kết nối cần kiểm tra lại nhóm tuổi.',403)
        values=(jid,uid,title,body,excerpt if audience!='privateOnly' else '',audience,conn['id'] if conn else None,
                int(bool_field(p,'anonymous')),int(bool_field(p,'commentsEnabled',True)),support,old['created'] if old else now)
        db.execute('''INSERT INTO journals VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
          title=excluded.title,body=excluded.body,shared_text=excluded.shared_text,audience=excluded.audience,
          connection_id=excluded.connection_id,anonymous=excluded.anonymous,comments_enabled=excluded.comments_enabled,support=excluded.support''',values)
        if audience!='community':
            db.execute('DELETE FROM comments WHERE journal_id=?',(jid,))
            db.execute('DELETE FROM listening WHERE journal_id=?',(jid,))
        return {'id':jid}
    if kind=='journal.delete':
        row=get_journal(db,p.get('id'),uid)
        if row['author_id']!=uid: fail('Không thể xóa bài này.',403)
        db.execute('DELETE FROM journals WHERE id=?',(row['id'],)); return {}
    if kind in ('journal.listen','journal.comment'):
        row=get_journal(db,p.get('id'),uid)
        if row['audience']!='community': fail('Bài này không công khai.',403)
        if kind=='journal.listen':
            if row['author_id']==uid: fail('Không tự lắng nghe bài của mình.')
            enabled=bool_field(p,'enabled',True)
            if enabled: db.execute('INSERT OR IGNORE INTO listening VALUES(?,?)',(row['id'],uid))
            else: db.execute('DELETE FROM listening WHERE journal_id=? AND user_id=?',(row['id'],uid))
        else:
            if not row['comments_enabled']: fail('Bài viết đã tắt phản hồi.',403)
            db.execute('INSERT INTO comments VALUES(?,?,?,?,?)',(new_id(),row['id'],uid,text_field(p,'text',2000),now))
        return {}
    if kind=='invitation.send':
        source=None
        if p.get('journalID'):
            source=get_journal(db,p['journalID'],uid)
            if source['audience']!='community': fail('Bài này không nhận lời mời.',403)
            target=source['author_id']
        else: target=identifier(p.get('userID'))
        if not can_invite(db,uid,target,now): fail('Cần xác minh tuổi, đúng nhóm tuổi và cả hai chưa có kết nối.',403)
        if db.execute('SELECT 1 FROM invitations WHERE (sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?)',(uid,target,target,uid)).fetchone(): fail('Đã có lời mời giữa hai người.',409)
        if db.execute('SELECT count(*) FROM invitations WHERE sender_id=?',(uid,)).fetchone()[0]>=20: fail('Tối đa 20 lời mời đang chờ.',409)
        iid=new_id();db.execute('INSERT INTO invitations VALUES(?,?,?,?,?,?)',(iid,uid,target,source['id'] if source else None,source['id'] if source and source['anonymous'] else None,now));return {'id':iid}
    if kind in ('invitation.accept','invitation.dismiss'):
        row=db.execute('SELECT * FROM invitations WHERE id=?',(identifier(p.get('id')),)).fetchone()
        if row is None or uid not in (row['sender_id'],row['recipient_id']): fail('Không tìm thấy lời mời.',404)
        if kind=='invitation.accept':
            if row['recipient_id']!=uid: fail('Chỉ người nhận được chấp nhận lời mời.',403)
            a,b=row['sender_id'],row['recipient_id']
            if not can_invite(db,a,b,now): fail('Kết nối không còn phù hợp hoặc đang có kết nối khác.',409)
            cid=new_id();db.execute('INSERT INTO connections(id,first_id,second_id,started) VALUES(?,?,?,?)',(cid,a,b,now))
            db.execute('DELETE FROM invitations WHERE sender_id IN (?,?) OR recipient_id IN (?,?)',(a,b,a,b))
            return {'id':cid}
        db.execute('DELETE FROM invitations WHERE id=?',(row['id'],));return {}
    if kind in ('message.send','connection.checkin','connection.pause','connection.leave'):
        conn=active(db,uid)
        if conn is None or conn['id']!=identifier(p.get('connectionID')): fail('Kết nối không hoạt động.',409)
        cid=conn['id']
        if kind!='connection.leave' and not eligible(db,conn['first_id'],conn['second_id'],now): fail('Kết nối cần kiểm tra lại nhóm tuổi.',403)
        if kind=='message.send':
            mid=new_id();db.execute('INSERT INTO messages VALUES(?,?,?,?,?)',(mid,cid,uid,text_field(p,'text',4000),now));return {'id':mid}
        if kind=='connection.leave': db.execute('UPDATE connections SET ended=? WHERE id=?',(now,cid))
        if kind=='connection.pause': db.execute('UPDATE connections SET paused=? WHERE id=?',(int(bool_field(p,'paused')),cid))
        if kind=='connection.checkin':
            if conn['paused']: fail('Khu vườn đang nghỉ.',409)
            today=datetime.fromtimestamp(now,timezone.utc).date();key=today.isoformat()
            db.execute('INSERT OR IGNORE INTO checkins VALUES(?,?,?)',(cid,uid,key))
            count=db.execute('SELECT count(*) FROM checkins WHERE connection_id=? AND day=?',(cid,key)).fetchone()[0]
            if count==2 and conn['last_complete_day']!=key:
                streak=conn['streak']+1 if conn['last_complete_day']==(today-timedelta(days=1)).isoformat() else 1
                db.execute('UPDATE connections SET total_days=total_days+1,streak=?,best_streak=max(best_streak,?),last_complete_day=? WHERE id=?',(streak,streak,key,cid))
        return {}
    if kind in ('user.block','report.create'):
        if p.get('journalID'):
            target=get_journal(db,p['journalID'],uid)['author_id']
        else: target=identifier(p.get('userID'))
        if target==uid or db.execute('SELECT 1 FROM users WHERE id=?',(target,)).fetchone() is None: fail('Người dùng không hợp lệ.')
        if kind=='user.block':
            db.execute('INSERT OR IGNORE INTO blocks VALUES(?,?)',(uid,target))
            db.execute('DELETE FROM invitations WHERE (sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?)',(uid,target,target,uid))
            db.execute('UPDATE connections SET ended=? WHERE ended IS NULL AND ((first_id=? AND second_id=?) OR (first_id=? AND second_id=?))',(now,uid,target,target,uid))
        else: db.execute('INSERT INTO reports(id,reporter_id,reported_id,reason,created) VALUES(?,?,?,?,?)',(new_id(),uid,target,text_field(p,'reason',1000),now))
        return {}
    if kind=='profile.update':
        nickname=text_field(p,'nickname',40); bio=text_field(p,'bio',500,default='',empty=True)
        interests=p.get('interests',[])
        if not isinstance(interests,list) or len(interests)>8 or any(not isinstance(x,str) or not 1<=len(x.strip())<=30 for x in interests): fail('Tối đa 8 sở thích, mỗi mục 1–30 ký tự.')
        support=p.get('support','Chỉ cần lắng nghe')
        if support not in SUPPORT: fail('Lựa chọn phản hồi không hợp lệ.')
        pace=text_field(p,'pace',80,default='Buổi tối')
        db.execute('UPDATE users SET nickname=?,bio=?,interests=?,support=?,pace=? WHERE id=?',(nickname,bio,json.dumps([x.strip() for x in interests],ensure_ascii=False),support,pace,uid));return {}
    fail('Thao tác không được hỗ trợ.')


def create_app(path: str | Path = 'data/dearly.sqlite3', *, clock: Callable[[],float] = time.time) -> FastAPI:
    database=Database(path); limiter=Limiter(); hashing=threading.BoundedSemaphore(2)
    @asynccontextmanager
    async def lifespan(app):
        anyio.to_thread.current_default_thread_limiter().total_tokens=16
        yield
    app=FastAPI(title='Dearly API',version='0.2.0',docs_url='/docs',redoc_url=None,lifespan=lifespan)
    app.state.database=database
    app.add_middleware(BodyLimit)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        # Do not reflect submitted credentials back in validation responses.
        return JSONResponse({'detail':'Thông tin chưa hợp lệ. Kiểm tra tên đăng nhập, mật khẩu và các trường bắt buộc.'},status_code=422)

    @app.exception_handler(sqlite3.OperationalError)
    async def database_busy(request,exc):
        return JSONResponse({'detail':'Dữ liệu đang bận. Thử lại sau.'},status_code=503,headers={'Retry-After':'1'})

    def authenticate(db,authorization):
        if not authorization or not authorization.startswith('Bearer ') or len(authorization)>512: fail('Cần đăng nhập.',401)
        digest=hashlib.sha256(authorization[7:].encode()).hexdigest()
        user=db.execute('SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires>? AND u.suspended=0',(digest,clock())).fetchone()
        if user is None: fail('Phiên đã hết hạn hoặc tài khoản bị khóa. Đăng nhập lại nhé.',401)
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
    def health(): return {'status':'ok','version':'0.2.0','dayBoundary':'UTC'}

    @app.post('/v1/auth/register',status_code=201)
    def register(data: Registration,request: Request):
        auth_rate(request,data.username)
        birth=validate_birth(data.birthDate,clock());nickname=data.nickname.strip()
        if not nickname: fail('Nickname không được trống.')
        if not hashing.acquire(blocking=False): fail('Đăng nhập đang bận. Thử lại sau.',429)
        try: encoded=password_hash(data.password)
        finally: hashing.release()
        with database.connect(write=True) as db:
            if db.execute('SELECT 1 FROM users WHERE username=?',(data.username.lower(),)).fetchone(): fail('Tên đăng nhập đã được sử dụng.',409)
            uid=new_id()
            db.execute('INSERT INTO users(id,username,password_hash,nickname,birth_date,created) VALUES(?,?,?,?,?,?)',(uid,data.username.lower(),encoded,nickname,birth,clock()))
            changed(db);return session(db,uid)

    @app.post('/v1/auth/login')
    def login(data: Credentials,request: Request):
        auth_rate(request,data.username)
        with database.connect() as db:
            user=db.execute('SELECT * FROM users WHERE username=?',(data.username.lower(),)).fetchone()
        # Fixed-cost dummy verification avoids a fast nonexistent-username path.
        dummy='pbkdf2-sha256$600000$'+'00'*16+'$'+'00'*32
        if not hashing.acquire(blocking=False): fail('Đăng nhập đang bận. Thử lại sau.',429)
        try: valid=password_matches(data.password,user['password_hash'] if user else dummy)
        finally: hashing.release()
        if not valid or user is None or user['suspended']: fail('Sai tên đăng nhập hoặc mật khẩu.',401)
        with database.connect(write=True) as db:
            if db.execute('SELECT suspended FROM users WHERE id=?',(user['id'],)).fetchone()[0]: fail('Tài khoản không khả dụng.',401)
            return session(db,user['id'])

    @app.post('/v1/auth/logout')
    def logout(authorization: str | None=Header(default=None)):
        with database.connect(write=True) as db:
            authenticate(db,authorization)
            db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(authorization[7:].encode()).hexdigest(),))
        return {'ok':True}

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

    @app.post('/v1/actions')
    def action(data: Action,authorization: str | None=Header(default=None)):
        rid=identifier(data.requestID)
        fingerprint=hashlib.sha256(json.dumps({'kind':data.kind,'payload':data.payload},sort_keys=True,separators=(',',':')).encode()).hexdigest()
        with database.connect(write=True) as db:
            user=authenticate(db,authorization);uid=user['id'];now=clock()
            limiter.check('write:'+uid,40,1)
            previous=db.execute('SELECT * FROM requests WHERE user_id=? AND request_id=?',(uid,rid)).fetchone()
            if previous:
                if previous['payload_hash']!=fingerprint: fail('ID yêu cầu đã dùng cho nội dung khác.',409)
                return json.loads(previous['result'])
            result={'ok':True,**apply_action(db,user,data.kind,data.payload,now)}
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?)',(uid,rid,fingerprint,json.dumps(result),now))
            db.execute('DELETE FROM requests WHERE created<?',(now-7*86400,))
            changed(db);return result

    @app.get('/v1/journals')
    def own_journals(before: str | None=None,limit: int=40,authorization: str | None=Header(default=None)):
        if not 1<=limit<=60: fail('limit phải từ 1 đến 60.')
        with database.connect() as db:
            user=authenticate(db,authorization);uid=user['id'];now=clock()
            limiter.check('read:'+uid,60,1)
            args=[uid];where='author_id=?'
            if before:
                cursor=db.execute('SELECT created,id FROM journals WHERE id=? AND author_id=?',(identifier(before),uid)).fetchone()
                if cursor is None: fail('Cursor không hợp lệ.')
                where+=' AND (created,id)<(?,?)';args.extend([cursor['created'],cursor['id']])
            rows=db.execute(f'SELECT * FROM journals WHERE {where} ORDER BY created DESC,id DESC LIMIT ?',(*args,limit+1)).fetchall()
            page=rows[:limit]
            return dict(items=[journal_dto(db,r,uid,now) for r in page],nextCursor=page[-1]['id'] if len(rows)>limit else None)

    @app.get('/v1/messages')
    def history(connectionID: str,before: str | None=None,limit: int=50,authorization: str | None=Header(default=None)):
        if not 1<=limit<=100: fail('limit phải từ 1 đến 100.')
        with database.connect() as db:
            user=authenticate(db,authorization);conn=active(db,user['id'])
            if conn is None or conn['id']!=identifier(connectionID): fail('Không có quyền đọc chat.',403)
            limiter.check('read:'+user['id'],60,1)
            args=[conn['id']];where='connection_id=?'
            if before:
                cursor=db.execute('SELECT created,id FROM messages WHERE id=? AND connection_id=?',(identifier(before),conn['id'])).fetchone()
                if cursor is None: fail('Cursor không hợp lệ.')
                where+=' AND (created,id)<(?,?)';args.extend([cursor['created'],cursor['id']])
            rows=db.execute(f'SELECT * FROM messages WHERE {where} ORDER BY created DESC,id DESC LIMIT ?',(*args,limit+1)).fetchall()
            page=rows[:limit]
            return dict(items=[message_dto(r) for r in reversed(page)],nextCursor=page[-1]['id'] if len(rows)>limit else None)

    return app
