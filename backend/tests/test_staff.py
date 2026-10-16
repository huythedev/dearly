"""Authorization boundaries, migration, operator commands, and staff workflows."""
import hashlib
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from server import Database, SCHEMA, changed, create_app, set_role
from test_api import action, journal, pair, register, state


def grant(env, uid, role):
    _, app, clock = env
    with app.state.database.connect(write=True) as db:
        user = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        set_role(db, user, role, 'server-cli', 'Test operator grant', clock[0])
        changed(db)


def cli(env, *args, expected=0):
    launcher = Path(__file__).resolve().parents[1] / 'run.py'
    result = subprocess.run([sys.executable, str(launcher), '--db', str(env[1].state.database.path), *args],
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == expected, result.stdout + result.stderr
    return result


@pytest.mark.parametrize('endpoint', ['reports', 'users', 'audit'])
def test_staff_reads_require_auth_and_role(env, endpoint):
    client, _, _ = env
    _, h = register(env, 'member')
    assert client.get('/v1/staff/' + endpoint).status_code == 401
    assert client.get('/v1/staff/' + endpoint, headers=h).status_code == 403
    snapshot = state(client, h)
    assert snapshot['currentUserRole'] == 'user' and snapshot['permissions'] == []
    assert all('role' not in p for p in snapshot['profiles'])


def test_registration_and_profile_cannot_assign_roles(env):
    client, _, _ = env
    body = dict(username='forged', password='test-password-123', nickname='Forged', birthDate='2000-01-01', role='admin')
    assert client.post('/v1/auth/register', json=body).status_code == 422
    user, h = register(env, 'member')
    action(client, h, 'profile.update', dict(nickname='Member', role='admin', permissions=['users.read']))
    assert state(client, h)['currentUserRole'] == 'user'
    for kind in ['staff.report.review', 'staff.report.hide', 'staff.user.role', 'staff.user.suspend', 'staff.user.verify_age']:
        action(client, h, kind, dict(userID=user['userID'], role='admin'), expected=403)


def test_moderator_reviews_report_without_private_content_or_account_access(env):
    client, _, _ = env
    owner, ho = register(env, 'owner'); reporter, hr = register(env, 'reporter'); mod, hm = register(env, 'mod')
    grant(env, mod['userID'], 'moderator')
    jid = journal(client, ho, anonymous=True)
    action(client, hr, 'report.create', dict(journalID=jid, reason='Unwanted pressure'))
    response = client.get('/v1/staff/reports', headers=hm)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    report = response.json()['items'][0]
    assert report['evidence'] == 'Public excerpt.' and report['canHide']
    assert 'PRIVATE PREFIX' not in response.text and 'PRIVATE TITLE' not in response.text
    assert 'password_hash' not in response.text and 'birthDate' not in response.text
    assert client.get('/v1/staff/users', headers=hm).status_code == 403
    assert client.get('/v1/staff/audit', headers=hm).status_code == 403
    for kind in ['staff.user.role', 'staff.user.suspend', 'staff.user.verify_age']:
        action(client, hm, kind, dict(userID=owner['userID'], reason='Attempt'), expected=403)
    action(client, hm, 'staff.report.review', dict(id=report['id'], status='reviewed', reason='Reviewed context'))
    assert client.get('/v1/staff/reports', headers=hm).json()['items'] == []
    reviewed = client.get('/v1/staff/reports', headers=hm, params={'status': 'reviewed'}).json()['items'][0]
    assert reviewed['reviewerID'] == mod['userID'] and reviewed['reviewNote'] == 'Reviewed context'
    action(client, hm, 'staff.report.review', dict(id=report['id'], status='open', reason='Needs another look'))
    assert len(client.get('/v1/staff/reports', headers=hm).json()['items']) == 1


def test_hide_reported_post_preserves_private_journal_and_moderation_hold(env):
    client, app, _ = env
    owner, ho = register(env, 'owner'); _, hr = register(env, 'reporter'); mod, hm = register(env, 'mod')
    grant(env, mod['userID'], 'moderator')
    jid = journal(client, ho, anonymous=True)
    action(client, hr, 'journal.comment', dict(id=jid, text='Comment'))
    action(client, hr, 'invitation.send', dict(journalID=jid), expected=403)
    action(client, hr, 'report.create', dict(journalID=jid, reason='Reported excerpt'))
    report = client.get('/v1/staff/reports', headers=hm).json()['items'][0]
    rid = str(uuid.uuid4()); payload = dict(id=report['id'], reason='Remove from community')
    action(client, hm, 'staff.report.hide', payload, rid=rid)
    action(client, hm, 'staff.report.hide', payload, rid=rid)
    assert all(j['id'] != jid for j in state(client, hr)['journals'])
    own = next(j for j in state(client, ho)['journals'] if j['id'] == jid)
    assert own['audience'] == 'privateOnly' and 'PRIVATE PREFIX' in own['body']
    assert state(client, hr)['invitations'] == []
    assert own['moderationHidden'] is True
    with app.state.database.connect() as db:
        assert db.execute('SELECT count(*) FROM comments WHERE journal_id=?', (jid,)).fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM audit_log WHERE action='report.hide'").fetchone()[0] == 1
    # Already-withdrawn content cannot be hidden again under a new mutation ID.
    action(client, hm, 'staff.report.hide', payload, expected=409)
    action(client, hr, 'report.create', dict(userID=owner['userID'], reason='Account report'))
    account = next(r for r in client.get('/v1/staff/reports', headers=hm).json()['items'] if not r['journalID'])
    assert account['evidence'] == '' and not account['canHide']
    action(client, hm, 'staff.report.hide', dict(id=account['id'], reason='No post'), expected=409)


def test_admin_account_management_and_live_demotion(env):
    client, app, _ = env
    admin, ha = register(env, 'admin'); member, hm = register(env, 'member', verified=False)
    grant(env, admin['userID'], 'admin')
    etag = client.get('/v1/state', headers=hm).headers['etag']
    action(client, ha, 'staff.user.role', dict(userID=member['userID'], role='moderator', reason='Trusted reviewer'))
    snapshot = client.get('/v1/state', headers={**hm, 'If-None-Match': etag})
    assert snapshot.status_code == 200 and snapshot.json()['state']['currentUserRole'] == 'moderator'
    assert client.get('/v1/staff/reports', headers=hm).status_code == 200
    action(client, ha, 'staff.user.verify_age', dict(userID=member['userID'], birthDate='2009-01-01', reason='Reviewed outside app'))
    accounts = client.get('/v1/staff/users', headers=ha, params={'q': 'member'}).json()['items']
    assert len(accounts) == 1 and accounts[0]['ageVerified']
    assert not {'password_hash', 'token', 'password'}.intersection(accounts[0])
    action(client, ha, 'staff.user.role', dict(userID=member['userID'], role='user', reason='End review duty'))
    assert client.get('/v1/staff/reports', headers=hm).status_code == 403
    assert state(client, hm)['permissions'] == []
    audit = client.get('/v1/staff/audit', headers=ha)
    assert audit.headers['cache-control'] == 'no-store'
    assert '2009-01-01' not in audit.text and 'test-password' not in audit.text
    assert any(e['detail'].get('to') == 'moderator' for e in audit.json()['items'])
    # No remote promotion to admin, modification of an admin, or self-modification.
    for target, role in [(member['userID'], 'admin'), (admin['userID'], 'user')]:
        action(client, ha, 'staff.user.role', dict(userID=target, role=role, reason='Escalation'), expected=403)
    action(client, ha, 'staff.user.suspend', dict(userID=admin['userID'], suspended=True, reason='Self lock'), expected=403)
    # Strict staff payloads and required notes.
    action(client, ha, 'staff.user.role', dict(userID=member['userID'], role='moderator', reason=' '), expected=400)
    action(client, ha, 'staff.user.role', dict(userID=member['userID'], role='moderator', reason='Valid', extra=True), expected=400)


def test_demotion_rechecks_permission_before_idempotent_replay(env):
    client, _, _ = env
    admin, ha = register(env, 'admin'); mod, hm = register(env, 'mod'); member, hu = register(env, 'member')
    grant(env, admin['userID'], 'admin'); grant(env, mod['userID'], 'moderator')
    action(client, hu, 'report.create', dict(userID=mod['userID'], reason='Report'))
    rid = client.get('/v1/staff/reports', headers=hm).json()['items'][0]['id']
    request_id = str(uuid.uuid4()); payload = dict(id=rid, status='reviewed', reason='Checked')
    action(client, hm, 'staff.report.review', payload, rid=request_id)
    action(client, ha, 'staff.user.role', dict(userID=mod['userID'], role='user', reason='Revoke access'))
    action(client, hm, 'staff.report.review', payload, rid=request_id, expected=403)


def test_admin_suspension_preserves_rewards_and_restore_requires_login(env):
    client, _, _ = env
    a, ha, b, hb, cid = pair(env)
    admin, hs = register(env, 'admin'); grant(env, admin['userID'], 'admin')
    action(client, ha, 'connection.checkin', dict(connectionID=cid)); action(client, hb, 'connection.checkin', dict(connectionID=cid))
    action(client, hs, 'staff.user.suspend', dict(userID=b['userID'], suspended=True, reason='Confirmed harassment'))
    assert client.get('/v1/state', headers=hb).status_code == 401
    archived = state(client, ha)['connections'][0]
    assert archived['endedAt'] is not None and archived['serverTotalDays'] == 1
    action(client, hs, 'staff.user.suspend', dict(userID=b['userID'], suspended=False, reason='Appeal reviewed'))
    assert client.get('/v1/state', headers=hb).status_code == 401
    assert client.post('/v1/auth/login', json=dict(username='bravo', password='test-password-123')).status_code == 200


def test_cli_bootstrap_and_last_admin_protection(env):
    client, app, _ = env
    a, ha = register(env, 'alice'); b, hb = register(env, 'bravo')
    cli(env, 'set-role', '--username', 'ALICE', '--role', 'admin', '--reason', 'Bootstrap administrator')
    assert state(client, ha)['currentUserRole'] == 'admin'
    cli(env, 'set-role', '--username', 'alice', '--role', 'user', '--reason', 'Unsafe removal', expected=1)
    cli(env, 'suspend', '--username', 'alice', expected=1)
    cli(env, 'set-role', '--username', 'bravo', '--role', 'admin', '--reason', 'Second administrator')
    cli(env, 'set-role', '--username', 'alice', '--role', 'moderator', '--reason', 'Change duties')
    assert state(client, ha)['currentUserRole'] == 'moderator'
    cli(env, 'suspend', '--username', 'alice')
    cli(env, 'restore', '--username', 'alice')
    assert client.get('/v1/state', headers=ha).status_code == 401
    with app.state.database.connect() as db:
        assert db.execute("SELECT count(*) FROM audit_log WHERE actor_id='server-cli'").fetchone()[0] == 5


def test_staff_pagination_with_equal_timestamps(env):
    client, app, clock = env
    admin, ha = register(env, 'admin'); other, ho = register(env, 'other'); grant(env, admin['userID'], 'admin')
    with app.state.database.connect(write=True) as db:
        for i in range(7):
            db.execute('INSERT INTO reports(id,reporter_id,reported_id,reason,created) VALUES(?,?,?,?,?)',
                       (str(uuid.uuid4()).upper(), other['userID'], admin['userID'], str(i), clock[0]))
    for endpoint, expected in [('reports', 7), ('users', 2), ('audit', 1)]:
        seen = set(); cursor = None
        while True:
            params = {'limit': 1}
            if cursor is not None: params['before'] = cursor
            r = client.get('/v1/staff/' + endpoint, headers=ha, params=params)
            assert r.status_code == 200, r.text
            data = r.json(); ids = {item['id'] for item in data['items']}
            assert not seen.intersection(ids); seen.update(ids)
            cursor = data['nextCursor']
            if cursor is None: break
        assert len(seen) == expected
    assert client.get('/v1/staff/users', headers=ha, params={'q': '%'}).json()['items'] == []
    assert client.get('/v1/staff/reports', headers=ha, params={'limit': 500}).status_code == 400


def test_schema_v1_upgrade_preserves_accounts_sessions_journals_and_reports(tmp_path):
    path = tmp_path / 'legacy.sqlite3'; uid = str(uuid.uuid4()).upper(); other = str(uuid.uuid4()).upper()
    jid = str(uuid.uuid4()).upper(); rid = str(uuid.uuid4()).upper(); token = 'legacy-token'
    with sqlite3.connect(path) as db:
        # SCHEMA deliberately retains the original table layout; migrations add v2 columns.
        db.executescript(SCHEMA + 'PRAGMA user_version=1;')
        for value in (uid, other):
            db.execute('INSERT INTO users(id,username,password_hash,nickname,birth_date,created) VALUES(?,?,?,?,?,?)',
                       (value, value, 'unchanged-password-hash', 'Legacy', '2000-01-01', 10))
        db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), uid, 9999999999))
        db.execute('INSERT INTO journals VALUES(?,?,?,?,?,?,?,?,?,?,?)', (jid, uid, 'Title', 'Private body', '', 'privateOnly', None, 0, 1, 'Chỉ cần lắng nghe', 10))
        db.execute('INSERT INTO reports VALUES(?,?,?,?,?,?)', (rid, other, uid, 'Legacy report', 10, 'open'))
    app = create_app(path)
    with TestClient(app) as client:
        snapshot = state(client, {'Authorization': 'Bearer ' + token})
        assert snapshot['currentUserRole'] == 'user' and snapshot['journals'][0]['body'] == 'Private body'
    # Reopening v3 is idempotent, including startup by a second operator process.
    Database(path)
    with app.state.database.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        report = db.execute('SELECT * FROM reports WHERE id=?', (rid,)).fetchone()
        assert report['reason'] == 'Legacy report' and report['journal_id'] is None and report['evidence'] == ''
        assert db.execute('SELECT password_hash FROM users WHERE id=?', (uid,)).fetchone()[0] == 'unchanged-password-hash'
