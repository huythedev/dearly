import ast
import json
import re
import sqlite3
from pathlib import Path
from string import Formatter

import pytest
from fastapi.testclient import TestClient

from localization import VIETNAMESE, response_language
from server import Database, LEGACY_SUPPORT, SCHEMA, create_app
from test_api import action, journal, register, state


@pytest.mark.parametrize('header,expected', [
    ('', 'en'), ('en', 'en'), ('vi-VN', 'vi'), ('fr', 'en'),
    ('en;q=0.9,vi;q=0.5', 'en'), ('en;q=0.5,vi;q=0.9', 'vi'),
    ('vi;q=0,en;q=1', 'en'), ('vi;q=invalid,en', 'en'),
    ('vi;q=2,en', 'en'), ('vi;q=NaN,en', 'en'), ('vi;q=0.8,en;q=0.8', 'vi'),
])
def test_language_negotiation(header, expected):
    assert response_language(header) == expected


@pytest.mark.parametrize('language,expected', [
    ('', 'Please log in.'), ('en', 'Please log in.'),
    ('vi-VN,en;q=0.5', 'Cần đăng nhập.'), ('fr', 'Please log in.'),
])
def test_errors_default_to_english_and_support_vietnamese(env, language, expected):
    client, _, _ = env
    response = client.get('/v1/state', headers={'Accept-Language': language})
    assert response.status_code == 401
    assert response.json() == {'detail': expected}
    assert response.headers['Content-Language'] == response_language(language)
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['Vary'] == 'Accept-Language'


def test_dynamic_field_errors_and_validation_use_translated_templates(env):
    client, _, _ = env
    _, headers = register(env, 'writer')
    vietnamese = {**headers, 'Accept-Language': 'vi'}
    errors = [
        ({'body': []}, 'Thiếu hoặc sai trường body.'),
        ({'body': ''}, 'body: cần từ 1 đến 20000 ký tự.'),
        ({'anonymous': 'false'}, 'anonymous phải là true/false.'),
    ]
    for payload, expected in errors:
        result = action(client, vietnamese, 'journal.save', {'body': 'Entry.', **payload}, expected=400)
        assert result['detail'] == expected
    response = client.post('/v1/auth/login', headers={'Accept-Language': 'vi'},
                           json={'username': 'writer', 'password': 'short', 'secret': 'NEVER REFLECT'})
    assert response.status_code == 422
    assert response.json()['detail'].startswith('Thông tin chưa hợp lệ.')
    assert 'short' not in response.text and 'NEVER REFLECT' not in response.text


def test_upload_rejection_uses_selected_language(env):
    client, _, _ = env
    for language, expected in [('en', 'Request is too large.'), ('vi', 'Yêu cầu quá lớn.')]:
        response = client.post('/v1/actions', headers={'Accept-Language': language}, content=b'x' * 131073)
        assert response.status_code == 413
        assert response.json()['detail'] == expected
        assert response.headers['Content-Language'] == language
        assert response.headers['Connection'] == 'close'


def test_support_identifiers_and_legacy_inputs_round_trip_without_changing_content(env):
    client, app, _ = env
    user, headers = register(env, 'writer')
    for legacy, canonical in LEGACY_SUPPORT.items():
        for value in (canonical, legacy):
            jid = journal(client, headers, body='Nội dung của Mây.', sharedText='', audience='privateOnly', support=value)
            entry = next(e for e in state(client, headers)['journals'] if e['id'] == jid)
            assert entry['support'] == canonical and entry['body'] == 'Nội dung của Mây.'
            action(client, headers, 'profile.update', dict(nickname='Mây', bio='Viết tiếng Việt.',
                   interests=['Âm nhạc của tôi'], support=value, pace='Khi rảnh'))
            profile = next(p for p in state(client, headers)['profiles'] if p['id'] == user['userID'])
            assert profile['support'] == canonical
            assert profile['nickname'] == 'Mây' and profile['bio'] == 'Viết tiếng Việt.'
            assert profile['interests'] == ['Âm nhạc của tôi'] and profile['pace'] == 'Khi rảnh'
    with app.state.database.connect() as db:
        assert {r[0] for r in db.execute('SELECT support FROM journals')} == set(LEGACY_SUPPORT.values())


def test_v3_upgrade_migrates_only_support_and_preserves_private_content(env):
    client, app, _ = env
    user, headers = register(env, 'writer')
    ids = [journal(client, headers, audience='privateOnly', support=value)
           for value in LEGACY_SUPPORT.values()]
    with app.state.database.connect(write=True) as db:
        db.execute("UPDATE users SET support=?,bio=?,interests=?,pace=? WHERE id=?",
                   ('Chia sẻ trải nghiệm', 'Hồ sơ gốc', '["Âm nhạc"]', 'Buổi tối', user['userID']))
        for jid, legacy in zip(ids, LEGACY_SUPPORT):
            db.execute('UPDATE journals SET support=?,body=? WHERE id=?', (legacy, 'Nhật ký riêng tư.', jid))
        db.execute('PRAGMA user_version=3')
    for _ in range(2):
        database = Database(app.state.database.path)
        with database.connect() as db:
            assert db.execute('PRAGMA user_version').fetchone()[0] == 4
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
            profile = db.execute('SELECT * FROM users WHERE id=?', (user['userID'],)).fetchone()
            assert profile['support'] == 'relate'
            assert profile['bio'] == 'Hồ sơ gốc' and profile['interests'] == '["Âm nhạc"]'
            assert profile['pace'] == 'Buổi tối'
            assert {r['support'] for r in db.execute('SELECT * FROM journals')} == set(LEGACY_SUPPORT.values())
            assert all(r[0] == 'Nhật ký riêng tư.' for r in db.execute('SELECT body FROM journals'))
    assert state(client, headers)['currentUserID'] == user['userID']


def test_registration_after_legacy_schema_upgrade_uses_english_defaults(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    legacy_schema = SCHEMA.replace('["Music","Reading"]', '["Âm nhạc","Đọc sách"]')
    legacy_schema = legacy_schema.replace("DEFAULT 'listen'", "DEFAULT 'Chỉ cần lắng nghe'")
    legacy_schema = legacy_schema.replace("DEFAULT 'Evenings'", "DEFAULT 'Buổi tối'")
    with sqlite3.connect(path) as db:
        db.executescript(legacy_schema + 'PRAGMA user_version=1;')
    app = create_app(path)
    with TestClient(app) as client:
        response = client.post('/v1/auth/register', json=dict(username='newaccount', password='password1234',
                               nickname='New member', birthDate='2000-01-01'))
        assert response.status_code == 201
        headers = {'Authorization': 'Bearer ' + response.json()['token']}
        profile = client.get('/v1/state', headers=headers).json()['state']['profiles'][0]
        assert profile['support'] == 'listen'
        assert profile['interests'] == ['Music', 'Reading'] and profile['pace'] == 'Evenings'


def test_english_catalog_and_error_templates_have_complete_vietnamese_translations():
    root = Path(__file__).resolve().parents[2]
    catalog = json.loads((root / 'ios/Dearly/Localizable.xcstrings').read_text())
    assert catalog['sourceLanguage'] == 'en'
    for key, entry in catalog['strings'].items():
        # Brand names and language badges can opt out of translation.
        if entry.get('shouldTranslate') is False or not entry.get('localizations'):
            continue
        source = entry['localizations']['en']['stringUnit']['value']
        translated = entry['localizations']['vi']['stringUnit']['value']
        assert source == key
        assert translated
        assert sorted(re.findall(r'%\d+\$@', source)) == sorted(re.findall(r'%\d+\$@', translated))
    project = (root / 'ios/Dearly.xcodeproj/project.pbxproj').read_text()
    assert 'developmentRegion = en;' in project
    for path in (root / 'ios/Dearly').rglob('*.swift'):
        source_keys = re.findall(r'\bL(?:F)?\("((?:[^"\\]|\\.)*)"', path.read_text())
        for raw in source_keys:
            key = json.loads('"' + raw + '"')
            assert key in catalog['strings'], (path, key)
    source = ast.parse((root / 'backend/server.py').read_text())
    messages = {node.args[0].value for node in ast.walk(source) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name) and node.func.id in ('fail', 'error_response')
                and node.args and isinstance(node.args[0], ast.Constant)}
    assert messages <= VIETNAMESE.keys()
    for message in messages:
        fields = lambda template: {name for _, name, _, _ in Formatter().parse(template) if name}
        assert fields(message) == fields(VIETNAMESE[message])
