"""Regression coverage for the security audit and adjacent correctness bugs."""
import json
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient

from server import BodyLimit, Database, changed, create_app
from test_api import action, journal, pair, register, state
from test_staff import grant


def test_anonymous_invitation_probes_never_link_named_candidates(env):
    client, _, _ = env
    author, ha = register(env, 'author')
    other, _ = register(env, 'other')
    _, hv = register(env, 'viewer')
    jid = journal(client, ha, anonymous=True)
    for target in (None, author['userID'], other['userID']):
        if target:
            action(client, hv, 'invitation.send', {'userID': target})
        denied = action(client, hv, 'invitation.send', {'journalID': jid}, expected=403)
        assert denied['detail'] == 'Bài ẩn danh không nhận lời mời. Hãy kết nối qua hồ sơ được chia sẻ.'
        dto = next(j for j in state(client, hv)['journals'] if j['id'] == jid)
        assert dto['authorID'] == jid and dto['canInviteAuthor'] is False


@pytest.mark.parametrize('kind', ['journal.hide', 'user.block'])
def test_anonymous_hiding_does_not_modify_named_relationships(env, kind):
    client, app, _ = env
    author, ha = register(env, 'author')
    _, _ = register(env, 'other')
    _, hv = register(env, 'viewer')
    jid = journal(client, ha, anonymous=True)
    another = journal(client, ha, anonymous=True)
    before = state(client, hv)
    action(client, hv, kind, {'id': jid} if kind == 'journal.hide' else {'journalID': jid})
    after = state(client, hv)
    assert set(before['suggestedUserIDs']) == set(after['suggestedUserIDs'])
    assert author['userID'] in after['suggestedUserIDs']
    assert after['blocks'] == before['blocks']
    assert jid not in {j['id'] for j in after['journals']}
    assert another in {j['id'] for j in after['journals']}
    with app.state.database.connect() as db:
        assert db.execute('SELECT count(*) FROM blocks').fetchone()[0] == 0


def test_named_block_cannot_probe_anonymous_author_or_replies(env):
    client, _, _ = env
    author, ha = register(env, 'author')
    _, hv = register(env, 'viewer')
    jid = journal(client, ha, anonymous=True)
    named = journal(client, ha)
    action(client, ha, 'journal.comment', {'id': jid, 'text': 'Anonymous author reply'})
    before = next(j for j in state(client, hv)['journals'] if j['id'] == jid)
    action(client, hv, 'user.block', {'userID': author['userID']})
    after = state(client, hv)
    assert next(j for j in after['journals'] if j['id'] == jid) == before
    assert named not in {j['id'] for j in after['journals']}
    assert next(c for c in after['comments'] if c['journalID'] == jid)['authorID'] == jid
    # Direct mutation access must agree with snapshot visibility.
    action(client, hv, 'journal.comment', {'id': jid, 'text': 'Reply without knowing the writer'})
    action(client, hv, 'report.create', {'journalID': jid, 'reason': 'Review story'})


def test_private_journal_preserves_its_authors_anonymous_sharing_preference(env):
    client, _, _ = env
    _, ha = register(env, 'author')
    _, hv = register(env, 'viewer')
    mod, hm = register(env, 'moderator')
    grant(env, mod['userID'], 'moderator')
    jid = journal(client, ha, anonymous=True)
    action(client, hv, 'report.create', {'journalID': jid, 'reason': 'Review'})
    rid = client.get('/v1/staff/reports', headers=hm).json()['items'][0]['id']
    action(client, hm, 'staff.report.hide', {'id': rid, 'reason': 'Restricted'})
    own = next(j for j in state(client, ha)['journals'] if j['id'] == jid)
    assert own['audience'] == 'privateOnly' and own['anonymous'] is True
    archived = next(j for j in client.get('/v1/journals', headers=ha).json()['items'] if j['id'] == jid)
    assert archived['anonymous'] is True


def test_moderation_hold_survives_edits_restart_and_requires_staff_restore(env):
    client, app, clock = env
    _, ha = register(env, 'author')
    _, hv = register(env, 'viewer')
    mod, hm = register(env, 'moderator')
    grant(env, mod['userID'], 'moderator')
    jid = journal(client, ha)
    action(client, hv, 'report.create', {'journalID': jid, 'reason': 'Review'})
    rid = client.get('/v1/staff/reports', headers=hm).json()['items'][0]['id']
    action(client, hm, 'staff.report.hide', {'id': rid, 'reason': 'Restricted'})
    for audience in ('community', 'companion'):
        action(client, ha, 'journal.save', {'id': jid, 'body': 'Changed body', 'sharedText': 'Changed', 'audience': audience}, expected=403)
    journal(client, ha, id=jid, audience='privateOnly', body='New private content', sharedText='')
    with TestClient(create_app(app.state.database.path, clock=lambda: clock[0])) as restarted:
        own = next(j for j in state(restarted, ha)['journals'] if j['id'] == jid)
        assert own['body'] == 'New private content' and own['moderationHidden']
        action(restarted, ha, 'staff.report.restore', {'id': rid, 'reason': 'Self restore'}, expected=403)
        report = restarted.get('/v1/staff/reports', headers=hm, params={'status': 'reviewed'}).json()['items'][0]
        assert report['canRestore'] and not report['canHide']
        action(restarted, hm, 'staff.report.restore', {'id': rid, 'reason': 'Appeal reviewed'})
        assert jid not in {j['id'] for j in state(restarted, hv)['journals']}
        journal(restarted, ha, id=jid)
        assert jid in {j['id'] for j in state(restarted, hv)['journals']}
    with app.state.database.connect() as db:
        assert db.execute("SELECT count(*) FROM audit_log WHERE action='report.restore'").fetchone()[0] == 1


@pytest.mark.parametrize('kind,base', [('profile.update', {'nickname': 'Viewer'}), ('journal.save', {'body': 'Content'})])
@pytest.mark.parametrize('bad', [[], {}, None, 5, True])
def test_support_type_validation_is_controlled_and_atomic(env, kind, base, bad):
    client, app, _ = env
    _, h = register(env, 'viewer')
    action(client, h, kind, {**base, 'support': bad}, expected=400)
    assert client.get('/health').status_code == 200
    with app.state.database.connect() as db:
        assert db.execute('SELECT count(*) FROM journals').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM requests').fetchone()[0] == 0


def test_garden_archive_pages_include_all_rewards_and_enforce_ownership(env):
    client, app, clock = env
    owner, ho, partner, hp, active_id = pair(env)
    outsider, hx = register(env, 'outsider')
    expected = set()
    with app.state.database.connect(write=True) as db:
        for i in range(45):
            cid = str(uuid.uuid4()).upper(); expected.add(cid)
            db.execute('''INSERT INTO connections(id,first_id,second_id,started,ended,total_days,best_streak)
                          VALUES(?,?,?,?,?,?,?)''', (cid, owner['userID'], partner['userID'], clock[0]-100, clock[0]-99, 30, 14))
        # Future-dated legacy archives must not push the current connection out of state.
        db.execute('UPDATE connections SET started=? WHERE id!=?', (clock[0]+100, active_id))
        changed(db)
    assert any(c['id'] == active_id and c['endedAt'] is None for c in state(client, ho)['connections'])
    seen = set(); before = None
    while True:
        r = client.get('/v1/connections', headers=ho, params={'limit': 7, **({'before': before} if before else {})})
        assert r.status_code == 200 and r.headers['cache-control'] == 'no-store'
        page = r.json()
        ids = {c['id'] for c in page['items']}
        assert not seen.intersection(ids)
        assert all(c['serverTotalDays'] == 30 and c['bestStreak'] == 14 for c in page['items'])
        assert {owner['userID'], partner['userID']} <= {p['id'] for p in page['profiles']}
        assert outsider['userID'] not in {p['id'] for p in page['profiles']}
        seen.update(ids); before = page['nextCursor']
        if not before: break
    assert seen == expected
    assert client.get('/v1/connections', headers=hx).json()['items'] == []
    assert client.get('/v1/connections', headers=hx, params={'before': next(iter(expected))}).status_code == 400
    assert client.get('/v1/connections', headers=hp, params={'limit': 51}).status_code == 400
    assert client.get('/v1/connections').status_code == 401


@pytest.mark.parametrize('new_status', ['reviewed', 'dismissed'])
def test_report_cursor_survives_concurrent_status_change(env, new_status):
    client, _, _ = env
    reporter, hr = register(env, 'reporter')
    mod, hm = register(env, 'moderator')
    grant(env, mod['userID'], 'moderator')
    for _ in range(3):
        action(client, hr, 'report.create', {'userID': mod['userID'], 'reason': 'Review'})
    first = client.get('/v1/staff/reports', headers=hm, params={'limit': 1}).json()
    cursor = first['nextCursor']
    action(client, hm, 'staff.report.review', {'id': cursor, 'status': new_status, 'reason': 'Another session'})
    following = client.get('/v1/staff/reports', headers=hm, params={'limit': 2, 'before': cursor})
    assert following.status_code == 200
    assert len(following.json()['items']) == 2
    assert cursor not in {r['id'] for r in following.json()['items']}


def test_suspended_comments_and_direct_post_mutations_are_hidden(env):
    client, _, _ = env
    author, ha = register(env, 'author')
    _, hv = register(env, 'viewer')
    mod, hm = register(env, 'moderator')
    grant(env, mod['userID'], 'admin')
    jid = journal(client, hv)
    suspended_post = journal(client, ha)
    action(client, ha, 'journal.comment', {'id': jid, 'text': 'Removed after suspension'})
    action(client, hm, 'staff.user.suspend', {'userID': author['userID'], 'suspended': True, 'reason': 'Review complete'})
    assert not state(client, hv)['comments']
    action(client, hv, 'journal.comment', {'id': suspended_post, 'text': 'Should not reach hidden content'}, expected=404)


def test_v2_migration_preserves_staff_hides_and_drops_anonymous_invites(env):
    client, app, clock = env
    author, ha = register(env, 'author')
    viewer, hv = register(env, 'viewer')
    jid = journal(client, ha, anonymous=True)
    with app.state.database.connect(write=True) as db:
        db.execute('INSERT INTO invitations VALUES(?,?,?,?,?,?)', (str(uuid.uuid4()).upper(), viewer['userID'], author['userID'], jid, jid, clock[0]))
        db.execute('''INSERT INTO audit_log(actor_id,action,target_id,detail,created) VALUES(?,?,?,?,?)''',
                   ('server-cli', 'report.hide', 'legacy-report', json.dumps({'journalID': jid, 'reason': 'Legacy hide'}), clock[0]))
        db.execute('DROP TABLE moderation_holds')
        db.execute('DROP TABLE hidden_posts')
        db.execute('PRAGMA user_version=2')
    migrated = create_app(app.state.database.path, clock=lambda: clock[0])
    with TestClient(migrated) as new_client:
        assert not state(new_client, hv)['invitations']
        assert jid not in {j['id'] for j in state(new_client, hv)['journals']}
        own = next(j for j in state(new_client, ha)['journals'] if j['id'] == jid)
        assert own['moderationHidden'] and own['body'].startswith('PRIVATE PREFIX')
        journal_payload = {'id': jid, 'body': 'New', 'sharedText': 'New', 'audience': 'community'}
        action(new_client, ha, 'journal.save', journal_payload, expected=403)
    Database(app.state.database.path)
    with app.state.database.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert not db.execute('PRAGMA foreign_key_check').fetchall()


def test_body_deadlines_admission_cleanup_and_health_reserve():
    async def exercise():
        received = []
        async def app(scope, receive, send):
            received.append(await receive())
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'ok'})
        def scope(ip='127.0.0.1', body=True):
            return {'type': 'http', 'headers': [(b'content-length', b'10')] if body else [], 'client': (ip, 1)}
        async def stuck():
            await anyio.sleep_forever()
        async def empty():
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        middleware = BodyLimit(app, idle_timeout=.1, total_timeout=.3, max_uploads=2, per_ip=1)
        outputs = [[], [], [], [], []]
        def sender(index):
            async def send(message): outputs[index].append(message)
            return send
        async with anyio.create_task_group() as group:
            group.start_soon(middleware, scope(), stuck, sender(0))
            group.start_soon(middleware, scope('127.0.0.2'), stuck, sender(1))
            await anyio.sleep(.01)
            await middleware(scope(), stuck, sender(2))
            await middleware(scope('127.0.0.3'), stuck, sender(3))
            await middleware(scope(body=False), empty, sender(4))
        assert [o[0]['status'] for o in outputs] == [408, 408, 429, 429, 200]
        assert middleware.uploads == 0 and middleware.clients == {}
        # Continuously arriving chunks must still hit the total deadline.
        async def trickle():
            await anyio.sleep(.025)
            return {'type': 'http.request', 'body': b'x', 'more_body': True}
        middleware = BodyLimit(app, idle_timeout=.1, total_timeout=.08)
        result = []
        async def send(message): result.append(message)
        await middleware(scope(), trickle, send)
        assert result[0]['status'] == 408
        assert middleware.uploads == 0 and middleware.clients == {}
        await middleware(scope(), empty, send)
        assert result[-2]['status'] == 200
    anyio.run(exercise)


def test_real_http_upload_limit_preserves_health_and_times_out(tmp_path):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    launcher = Path(__file__).resolve().parents[1] / 'run.py'
    process = subprocess.Popen([sys.executable, str(launcher), '--db', str(tmp_path / 'http.sqlite3'),
                                'serve', '--port', str(port), '--body-idle-timeout', '1', '--body-total-timeout', '2'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    held = []
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=3, trust_env=False) as client:
            for _ in range(100):
                if process.poll() is not None: raise AssertionError('Local server exited')
                try:
                    if client.get('/health').status_code == 200: break
                except httpx.ConnectError: pass
                time.sleep(.03)
            else: raise AssertionError('Local server did not start')
            for _ in range(8):
                sock = socket.create_connection(('127.0.0.1', port), timeout=3)
                sock.sendall(b'POST /v1/auth/login HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: 1000\r\n\r\n{')
                held.append(sock)
            assert client.get('/health').status_code == 200
            assert client.post('/v1/auth/login', json={'username': 'test', 'password': 'password-123'}).status_code == 429
            for sock in held:
                assert b'408' in sock.recv(4096).split(b'\r\n', 1)[0]
            assert client.get('/health').status_code == 200
            registered = client.post('/v1/auth/register', json={'username': 'fresh', 'nickname': 'Fresh', 'password': 'password-123', 'birthDate': '2000-01-01'})
            assert registered.status_code == 201
    finally:
        for sock in held: sock.close()
        process.terminate()
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
