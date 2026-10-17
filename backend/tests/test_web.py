import uuid
from copy import copy
from contextlib import ExitStack
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from server import create_app
from test_api import action, pair, register
from test_staff import grant


WEB = {'X-Dearly-Client': 'web', 'Origin': 'http://testserver'}


def test_management_documents_require_current_staff_access_including_browser_cookies(tmp_path):
    dist = tmp_path / 'dist'; dist.mkdir()
    (dist / 'index.html').write_text('<html>DEARLY MANAGEMENT SHELL</html>')
    app = create_app(tmp_path / 'db.sqlite3', web_dir=dist)
    with TestClient(app) as client:
        env = client, app, [0]
        member, hm = register(env, 'member', verified=False)
        mod, hs = register(env, 'mod', verified=False)
        grant(env, mod['userID'], 'moderator')
        for path in ['/management', '/management/', '/management/accounts', '/management?section=users']:
            for headers, status in [({}, 401), (hm, 403), (hs, 200)]:
                response = client.get(path, headers=headers)
                assert response.status_code == status
                assert response.headers['cache-control'] == 'no-store'
                assert ('DEARLY MANAGEMENT SHELL' in response.text) == (status == 200)
        response = client.post('/v1/auth/login', headers=WEB, json={'username': 'mod', 'password': 'test-password-123'})
        assert response.status_code == 200
        assert client.get('/management').status_code == 200
        grant(env, mod['userID'], 'user')
        assert client.get('/management').status_code == 403
        client.post('/v1/auth/logout', headers=WEB)
        assert client.get('/management').status_code == 401


@pytest.mark.parametrize('endpoint', ['register', 'login'])
def test_browser_session_survives_reopening_until_its_server_expiry(env, endpoint):
    client, app, clock = env
    fields = {'username': 'persistent', 'password': 'test-password-123'}
    if endpoint == 'login':
        register(env, fields['username'])
    else:
        fields.update(nickname='Persistent', birthDate='2000-01-01')
    response = client.post('/v1/auth/' + endpoint, headers=WEB, json=fields)
    assert response.is_success
    cookie = SimpleCookie()
    cookie.load(response.headers['set-cookie'])
    assert int(cookie['dearly_session']['max-age']) == 30 * 86400
    expires = parsedate_to_datetime(cookie['dearly_session']['expires']).timestamp()
    assert expires == response.json()['expiresAt'] + 978307200
    # Browsers discard session-only cookies when a browser session ends.
    persistent = [copy(item) for item in client.cookies.jar if not item.discard]
    assert persistent
    with TestClient(app) as reopened:
        for item in persistent:
            reopened.cookies.jar.set_cookie(item)
        assert reopened.get('/v1/state').json()['state']['currentUserID'] == response.json()['userID']
        clock[0] += 30 * 86400 + 1
        assert reopened.get('/v1/state').status_code == 401


def test_browser_sessions_keep_tokens_out_of_javascript_and_preserve_native_contract(env):
    client, _, _ = env
    native, headers = register(env, 'native')
    assert native['token']
    response = client.post('/v1/auth/register', headers=WEB,
                           json={'username': 'browser', 'password': 'test-password-123',
                                 'nickname': 'Browser', 'birthDate': '2009-01-01'})
    assert response.status_code == 201
    assert 'token' not in response.json()
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Path=/' in cookie
    assert client.get('/v1/state').json()['state']['currentUserID'] == response.json()['userID']
    assert client.get('/v1/state', headers=headers).json()['state']['currentUserID'] == native['userID']
    assert client.post('/v1/auth/logout', headers=WEB).status_code == 200
    assert client.get('/v1/state').status_code == 401
    assert client.get('/v1/state', headers=headers).status_code == 200


def test_browser_cookie_writes_and_logins_reject_cross_origin_requests(env):
    client, _, _ = env
    register(env, 'browser')
    fields = {'username': 'browser', 'password': 'test-password-123'}
    assert client.post('/v1/auth/login', headers={**WEB, 'Origin': 'https://evil.example'}, json=fields).status_code == 403
    response = client.post('/v1/auth/login', headers=WEB, json=fields)
    assert 'token' not in response.json()
    payload = {'requestID': str(uuid.uuid4()), 'kind': 'profile.update', 'payload': {'nickname': 'Changed'}}
    assert client.post('/v1/actions', json=payload).status_code == 403
    assert client.post('/v1/actions', headers={**WEB, 'Origin': 'http://evil.example'}, json=payload).status_code == 403
    assert client.post('/v1/actions', headers=WEB, json=payload).status_code == 200


def test_https_browser_session_cookie_is_secure(env):
    client, app, _ = env
    register(env, 'browser')
    with TestClient(app, base_url='https://dearly.example') as secure:
        response = secure.post('/v1/auth/login', headers={'X-Dearly-Client': 'web', 'Origin': 'https://dearly.example'},
                               json={'username': 'browser', 'password': 'test-password-123'})
        assert 'Secure' in response.headers['set-cookie']
        assert secure.get('/v1/state').status_code == 200


def test_spa_serving_reserves_api_routes_and_never_exposes_repository_files(tmp_path):
    dist = tmp_path / 'dist'; dist.mkdir()
    (dist / 'assets').mkdir()
    (dist / 'index.html').write_text('<html>DEARLY SPA</html>')
    (dist / 'favicon.svg').write_text('<svg/>')
    (dist / 'assets/app-test.js').write_text('console.log("test")')
    (tmp_path / 'secret.txt').write_text('private')
    with TestClient(create_app(tmp_path / 'db.sqlite3', web_dir=dist)) as client:
        for path in ('/', '/journal', '/community', '/companion', '/settings'):
            response = client.get(path)
            assert response.status_code == 200 and 'DEARLY SPA' in response.text
            assert 'no-cache' in response.headers['cache-control']
            assert "frame-ancestors 'none'" in response.headers['content-security-policy']
        assert client.get('/favicon.svg').status_code == 200
        assert client.get('/assets/app-test.js').status_code == 200
        for path in ('/v1/missing', '/ws/missing', '/assets/missing.js', '/missing.js', '/.env', '/%2e%2e/secret.txt'):
            response = client.get(path)
            assert response.status_code == 404 and 'DEARLY SPA' not in response.text and 'private' not in response.text
        assert client.get('/health').json()['status'] == 'ok'
        assert 'swagger-ui' in client.get('/docs').text
        assert client.get('/v1/state').status_code == 401
    with pytest.raises(ValueError):
        create_app(tmp_path / 'other.sqlite3', web_dir=tmp_path / 'missing')


def socket_auth(socket, token):
    socket.send_json({'type': 'authenticate', 'token': token})
    assert socket.receive_json()['type'] == 'ready'


def receive_type(socket, kind):
    for _ in range(10):
        frame = socket.receive_json()
        if frame['type'] == kind:
            return frame
    pytest.fail(f'Did not receive {kind}')


def test_websocket_messages_reach_only_active_members_and_share_rest_idempotency(env):
    client, _, _ = env
    a, ha, b, _, cid = pair(env)
    outsider, _ = register(env, 'outsider')
    with client.websocket_connect('/ws/chat') as first, client.websocket_connect('/ws/chat') as second, client.websocket_connect('/ws/chat') as third:
        socket_auth(first, a['token']); socket_auth(second, b['token']); socket_auth(third, outsider['token'])
        rid = str(uuid.uuid4())
        first.send_json({'type': 'message.send', 'requestID': rid, 'connectionID': cid.lower(), 'text': 'A live hello'})
        ack = receive_type(first, 'ack')
        message = receive_type(second, 'message')['message']
        assert message['text'] == 'A live hello' and message['id'] == ack['result']['id']
        replay = action(client, ha, 'message.send', {'connectionID': cid.lower(), 'text': 'A live hello'}, rid=rid)
        assert replay['id'] == message['id']
        assert len(client.get('/v1/messages', params={'connectionID': cid}, headers=ha).json()['items']) == 1
        third.send_json({'type': 'ping'})
        assert third.receive_json()['type'] == 'pong'
        # Native REST sends also wake an already connected browser/native socket.
        action(client, ha, 'message.send', {'connectionID': cid, 'text': 'From the iPhone'})
        assert receive_type(second, 'message')['message']['text'] == 'From the iPhone'


def test_websocket_browser_cookie_requires_same_origin(env):
    client, _, _ = env
    register(env, 'browser')
    client.post('/v1/auth/login', headers=WEB, json={'username': 'browser', 'password': 'test-password-123'})
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws/chat', headers={'Origin': 'http://evil.example'}):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws/chat'):
            pass
    with client.websocket_connect('/ws/chat', headers={'Origin': 'http://testserver'}) as socket:
        socket.send_json({'type': 'authenticate'})
        assert socket.receive_json()['type'] == 'ready'
        client.post('/v1/auth/logout', headers=WEB)
        with pytest.raises(WebSocketDisconnect) as disconnected:
            socket.receive_json()
        assert disconnected.value.code == 4401


def test_socket_rechecks_connection_and_revocation_before_writes(env):
    client, _, clock = env
    a, ha, _, hb, cid = pair(env)
    with client.websocket_connect('/ws/chat') as socket:
        socket_auth(socket, a['token'])
        action(client, hb, 'connection.leave', {'connectionID': cid})
        socket.send_json({'type': 'message.send', 'requestID': str(uuid.uuid4()), 'connectionID': cid, 'text': 'Too late'})
        assert receive_type(socket, 'error')['status'] == 409
        assert client.get('/v1/messages', params={'connectionID': cid}, headers=ha).status_code == 403
        clock[0] += 31 * 86400
        socket.send_json({'type': 'ping'})
        with pytest.raises(WebSocketDisconnect) as disconnected:
            socket.receive_json()
        assert disconnected.value.code == 4401


def test_invalid_socket_frames_never_mutate_and_size_is_bounded(env):
    client, _, _ = env
    a, ha, _, _, cid = pair(env)
    with client.websocket_connect('/ws/chat') as socket:
        socket_auth(socket, a['token'])
        socket.send_json({'type': 'message.send', 'requestID': 'bad', 'connectionID': cid, 'text': 'Rejected'})
        assert socket.receive_json()['status'] == 400
        assert client.get('/v1/messages', params={'connectionID': cid}, headers=ha).json()['items'] == []
        socket.send_text('x' * 32769)
        with pytest.raises(WebSocketDisconnect) as disconnected:
            socket.receive_json()
        assert disconnected.value.code == 1009


def test_socket_session_is_revoked_on_suspension(env):
    client, app, _ = env
    a, _ = register(env, 'browser')
    with client.websocket_connect('/ws/chat') as socket:
        socket_auth(socket, a['token'])
        with app.state.database.connect(write=True) as db:
            db.execute('UPDATE users SET suspended=1 WHERE id=?', (a['userID'],))
        socket.send_json({'type': 'ping'})
        with pytest.raises(WebSocketDisconnect) as disconnected:
            socket.receive_json()
        assert disconnected.value.code == 4401


def test_chat_has_a_per_account_connection_budget_and_releases_slots(env):
    client, _, _ = env
    a, _ = register(env, 'browser')
    with ExitStack() as stack:
        for _ in range(4):
            socket_auth(stack.enter_context(client.websocket_connect('/ws/chat')), a['token'])
        with client.websocket_connect('/ws/chat') as extra:
            extra.send_json({'type': 'authenticate', 'token': a['token']})
            with pytest.raises(WebSocketDisconnect) as disconnected:
                extra.receive_json()
            assert disconnected.value.code == 4429
    with client.websocket_connect('/ws/chat') as available:
        socket_auth(available, a['token'])


def test_browser_mutation_is_bound_to_the_account_that_created_it(env):
    client, _, _ = env
    first, _ = register(env, 'first_tab')
    second, _ = register(env, 'second_tab')
    fields = {'password': 'test-password-123'}
    assert client.post('/v1/auth/login', headers=WEB, json={**fields, 'username': 'first_tab'}).status_code == 200
    payload = {'requestID': str(uuid.uuid4()), 'kind': 'profile.update', 'payload': {'nickname': 'First account only'}}
    headers = {**WEB, 'X-Dearly-User': first['userID']}
    assert client.post('/v1/actions', headers=headers, json=payload).status_code == 200
    # Another tab switches the shared cookie before a lost reply is retried.
    assert client.post('/v1/auth/login', headers=WEB, json={**fields, 'username': 'second_tab'}).status_code == 200
    retry = client.post('/v1/actions', headers=headers, json=payload)
    assert retry.status_code == 409
    assert 'account changed' in retry.json()['detail']
    state = client.get('/v1/state').json()['state']
    assert state['currentUserID'] == second['userID']
    assert next(p for p in state['profiles'] if p['id'] == second['userID'])['nickname'] != 'First account only'
    # Reject before recording the request ID for the new account.
    assert client.post('/v1/actions', headers={**WEB, 'X-Dearly-User': second['userID']}, json=payload).status_code == 200


def test_socket_revocation_handles_a_client_that_already_disconnected(env):
    import asyncio
    import json

    import anyio

    _, app, _ = env
    session, _ = register(env, 'disconnecting')

    async def exercise():
        incoming = asyncio.Queue()
        incoming.put_nowait({'type': 'websocket.connect'})
        incoming.put_nowait({'type': 'websocket.receive', 'text': json.dumps({'type': 'authenticate', 'token': session['token']})})
        sent = []

        async def send(message):
            sent.append(message)
            if message['type'] == 'websocket.send':
                assert json.loads(message['text'])['type'] == 'ready'
                # Logout revokes the session as the browser closes its socket.
                with app.state.database.connect(write=True) as db:
                    db.execute('DELETE FROM sessions WHERE user_id=?', (session['userID'],))
                incoming.put_nowait({'type': 'websocket.disconnect', 'code': 1000})
            elif message['type'] == 'websocket.close':
                raise OSError('The browser already disconnected.')

        scope = {'type': 'websocket', 'path': '/ws/chat', 'raw_path': b'/ws/chat',
                 'root_path': '', 'scheme': 'ws', 'query_string': b'',
                 'headers': [(b'host', b'testserver')], 'client': ('127.0.0.1', 12345),
                 'server': ('testserver', 80), 'subprotocols': [], 'state': {},
                 'asgi': {'version': '3.0', 'spec_version': '2.4'}}
        await asyncio.wait_for(app(scope, incoming.get, send), timeout=2)
        assert sent[-1] == {'type': 'websocket.close', 'code': 4401, 'reason': ''}

    anyio.run(exercise)
