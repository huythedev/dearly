"""Adversarial account lifecycle and ciphertext transport checks on disposable DBs."""

import copy
import json
import uuid
from pathlib import Path

import pytest

from crypto_helpers import PREFIX, b64, identity, open_content, seal
from test_api import action, journal, pair, register, state
from test_staff import grant
from test_web import receive_type, socket_auth

PASSWORD = "test-password-123"


def publish(client, headers, who):
    data = {
        k: who["bundle"][k]
        for k in ["agreementKey", "signingKey", "wrappedPrivate", "nonce"]
    }
    response = client.post("/v1/encryption/identity", headers=headers, json=data)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == who["bundle"]
    return data


def test_key_publication_is_immutable_private_and_account_bound(env):
    client, _, _ = env
    a, ha = register(env, "alice")
    b, hb = register(env, "bravo")
    who = identity(a["userID"])
    assert client.get("/v1/encryption/identity", headers=ha).status_code == 404
    data = publish(client, ha, who)
    assert (
        client.post("/v1/encryption/identity", headers=ha, json=data).status_code == 200
    )
    assert (
        client.post(
            "/v1/encryption/identity",
            headers=ha,
            json={**data, "nonce": b64(b"1" * 12)},
        ).status_code
        == 409
    )
    assert client.get("/v1/encryption/identity").status_code == 401
    assert (
        client.get(
            "/v1/encryption/identity", headers={**ha, "X-Dearly-User": b["userID"]}
        ).status_code
        == 409
    )
    assert (
        client.get("/v1/encryption/keys/" + a["userID"], headers=hb).status_code == 404
    )
    assert (
        client.post(
            "/v1/encryption/identity",
            headers=hb,
            json={**data, "agreementKey": b64(b"\x04" + b"\0" * 64)},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/v1/encryption/identity", headers=hb, json={**data, "role": "admin"}
        ).status_code
        == 422
    )


def test_encrypted_journal_and_anonymous_public_excerpt_never_leak_body_or_real_id(env):
    client, app, _ = env
    a, ha = register(env, "alice")
    _, hb = register(env, "bravo")
    who = identity(a["userID"])
    publish(client, ha, who)
    jid = str(uuid.uuid4()).upper()
    wire = seal(
        who,
        [who],
        "journal",
        jid,
        "",
        dict(title="Secret title", body="PRIVATE WORDS. Public passage."),
    )
    action(
        client,
        ha,
        "journal.save",
        dict(
            clientID=jid,
            title="",
            body=wire,
            audience="community",
            anonymous=True,
            sharedText="Public passage.",
        ),
    )
    own = next(row for row in state(client, ha)["journals"] if row["id"] == jid)
    other = next(row for row in state(client, hb)["journals"] if row["id"] == jid)
    assert own["body"] == wire and own["title"] == ""
    assert other["body"] == other["title"] == "" and other["authorID"] == jid
    assert other["sharedText"] == "Public passage."
    assert a["userID"] not in json.dumps(other) and "PRIVATE WORDS" not in json.dumps(
        state(client, hb)
    )
    with app.state.database.connect() as db:
        row = db.execute("SELECT * FROM journals WHERE id=?", (jid,)).fetchone()
        assert (
            row["body"] == wire
            and row["title"] == ""
            and "PRIVATE WORDS" not in row["body"]
        )
    action(client, ha, "journal.save", dict(body="Plaintext downgrade"), expected=409)
    action(client, hb, "journal.save", dict(id=jid, body=wire), expected=403)


@pytest.mark.parametrize(
    "field",
    [
        "signature",
        "ciphertext",
        "ephemeralKey",
        "nonce",
        "salt",
        "senderKeyID",
        "id",
        "connectionID",
        "senderID",
        "purpose",
    ],
)
def test_ciphertext_tampering_and_resource_replay_roll_back(env, field):
    client, app, _ = env
    a, ha, b, hb, cid = pair(env)
    alice = identity(a["userID"])
    bob = identity(b["userID"], 31)
    publish(client, ha, alice)
    publish(client, hb, bob)
    mid = str(uuid.uuid4()).upper()
    wire = seal(alice, [alice, bob], "message", mid, cid, {"text": "Secret message"})
    e = json.loads(wire[len(PREFIX) :])
    e[field] = ("B" if str(e[field]).startswith("A") else "A") + e[field][1:]
    response = action(
        client,
        ha,
        "message.send",
        dict(clientID=mid, connectionID=cid, text=PREFIX + json.dumps(e)),
        expected=400 if field != "senderKeyID" else 409,
    )
    assert "Secret message" not in response["detail"]
    with app.state.database.connect() as db:
        assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 0


@pytest.mark.parametrize(
    "change", ["duplicate", "outsider", "missing", "wrong-key", "wrapped-key"]
)
def test_invalid_recipient_sets_never_commit(env, change):
    client, app, _ = env
    a, ha, b, hb, cid = pair(env)
    alice = identity(a["userID"])
    bob = identity(b["userID"], 31)
    publish(client, ha, alice)
    publish(client, hb, bob)
    mid = str(uuid.uuid4()).upper()
    e = json.loads(
        seal(alice, [alice, bob], "message", mid, cid, {"text": "Private"})[
            len(PREFIX) :
        ]
    )
    if change == "duplicate":
        e["recipients"][1] = copy.deepcopy(e["recipients"][0])
    if change == "outsider":
        e["recipients"][1]["userID"] = str(uuid.uuid4()).upper()
    if change == "missing":
        e["recipients"].pop()
    if change == "wrong-key":
        e["recipients"][1]["keyID"] = "0" * 64
    if change == "wrapped-key":
        e["recipients"][1]["wrappedKey"] = b64(b"\0" * 48)
    action(
        client,
        ha,
        "message.send",
        dict(clientID=mid, connectionID=cid, text=PREFIX + json.dumps(e)),
        expected=409 if change == "wrong-key" else 400,
    )
    with app.state.database.connect() as db:
        assert not db.execute("SELECT 1 FROM messages").fetchone()


def test_encrypted_socket_rest_retry_and_companion_passage_interoperate(env):
    client, app, _ = env
    a, ha, b, hb, cid = pair(env)
    alice = identity(a["userID"])
    bob = identity(b["userID"], 31)
    publish(client, ha, alice)
    publish(client, hb, bob)
    peer = client.get("/v1/encryption/keys/" + a["userID"], headers=hb).json()
    assert "wrappedPrivate" not in peer and "nonce" not in peer
    mid = str(uuid.uuid4()).upper()
    rid = str(uuid.uuid4())
    wire = seal(alice, [alice, bob], "message", mid, cid, {"text": "Mình ở đây 🌿"})
    payload = dict(clientID=mid, connectionID=cid, text=wire)
    with (
        client.websocket_connect("/ws/chat") as first,
        client.websocket_connect("/ws/chat") as second,
    ):
        socket_auth(first, a["token"])
        socket_auth(second, b["token"])
        first.send_json(dict(type="message.send", requestID=rid, **payload))
        assert receive_type(first, "ack")["result"]["id"] == mid
        message = receive_type(second, "message")["message"]
        assert open_content(bob, alice, message["text"]) == {"text": "Mình ở đây 🌿"}
        assert action(client, ha, "message.send", payload, rid=rid)["id"] == mid
    jid = str(uuid.uuid4()).upper()
    body = seal(
        alice,
        [alice],
        "journal",
        jid,
        "",
        {"title": "Thought", "body": "A private body"},
    )
    passage = seal(alice, [alice, bob], "passage", jid, cid, {"text": "private"})
    action(
        client,
        ha,
        "journal.save",
        dict(
            clientID=jid, title="", body=body, sharedText=passage, audience="companion"
        ),
    )
    shared = next(j for j in state(client, hb)["journals"] if j["id"] == jid)
    assert shared["body"] == "" and open_content(bob, alice, shared["sharedText"]) == {
        "text": "private"
    }
    action(
        client,
        hb,
        "message.send",
        dict(connectionID=cid, text="Downgrade"),
        expected=409,
    )
    with app.state.database.connect() as db:
        assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 1


def test_export_requires_password_and_never_deanonymizes_reports_or_exports_others_secrets(
    env,
):
    client, _, _ = env
    a, ha, b, hb, cid = pair(env)
    outsider, ho = register(env, "outsider")
    jid = journal(client, ho, anonymous=True)
    journal(client, ho, audience="privateOnly", body="OUTSIDER SECRET", sharedText="")
    mine = journal(
        client, ha, audience="privateOnly", body="MY PRIVATE WORDS", sharedText=""
    )
    action(client, ha, "report.create", dict(journalID=jid, reason="Please review"))
    action(client, ha, "message.send", dict(connectionID=cid, text="My sent message"))
    action(
        client,
        hb,
        "message.send",
        dict(connectionID=cid, text="Companion authored message"),
    )
    assert (
        client.post(
            "/v1/account/export", headers=ha, json={"password": "incorrect-password"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/account/export",
            headers={**ha, "X-Dearly-User": b["userID"]},
            json={"password": PASSWORD},
        ).status_code
        == 409
    )
    response = client.post(
        "/v1/account/export", headers=ha, json={"password": PASSWORD}
    )
    assert (
        response.status_code == 200 and response.headers["cache-control"] == "no-store"
    )
    value = response.json()
    raw = response.text
    assert (
        value["profile"]["id"] == a["userID"]
        and value["profile"]["username"] == "alice"
    )
    assert [j["id"] for j in value["journals"]] == [mine]
    assert value["messages"][0]["text"] == "My sent message"
    assert "Companion authored message" not in raw and "OUTSIDER SECRET" not in raw
    assert (
        outsider["userID"] not in raw
        and "reportedID" not in raw
        and "reported_id" not in raw
    )
    for secret in [
        "password_hash",
        "token_hash",
        a["token"],
        b["token"],
        "payload_hash",
    ]:
        assert secret not in raw


def test_account_deletion_erases_content_revokes_all_sessions_and_preserves_partner_rewards(
    env,
):
    client, app, _ = env
    a, ha, b, hb, cid = pair(env)
    fresh = client.post(
        "/v1/auth/login", json=dict(username="alice", password=PASSWORD)
    ).json()
    jid = journal(client, ha)
    action(
        client,
        hb,
        "journal.comment",
        dict(id=jid, text="Other comment on deleted story"),
    )
    action(
        client,
        hb,
        "report.create",
        dict(journalID=jid, reason="Copied private identifying note"),
    )
    action(client, ha, "message.send", dict(connectionID=cid, text="ERASE MY MESSAGE"))
    action(client, hb, "message.send", dict(connectionID=cid, text="KEEP MY MESSAGE"))
    action(client, ha, "connection.checkin", dict(connectionID=cid))
    action(client, hb, "connection.checkin", dict(connectionID=cid))
    publish(client, ha, identity(a["userID"]))
    assert (
        client.post(
            "/v1/account/delete",
            headers=ha,
            json=dict(password=PASSWORD, confirmation="delete"),
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v1/account/delete",
            headers=ha,
            json=dict(password="wrong-password", confirmation="DELETE"),
        ).status_code
        == 403
    )
    with client.websocket_connect("/ws/chat") as socket:
        socket_auth(socket, a["token"])
        deleted = client.post(
            "/v1/account/delete",
            headers=ha,
            json=dict(password=PASSWORD, confirmation="DELETE"),
        )
        assert deleted.status_code == 200
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            while True:
                socket.receive_json()
    for token in [a["token"], fresh["token"]]:
        assert (
            client.get(
                "/v1/state", headers={"Authorization": "Bearer " + token}
            ).status_code
            == 401
        )
    with app.state.database.connect() as db:
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        user = db.execute("SELECT * FROM users WHERE id=?", (a["userID"],)).fetchone()
        assert (
            user["nickname"] == "Deleted account"
            and user["deleted_at"]
            and user["suspended"]
        )
        assert (
            user["username"] != "alice"
            and user["birth_date"] == "1900-01-01"
            and user["bio"] == ""
        )
        for table, field in [
            ("journals", "author_id"),
            ("messages", "sender_id"),
            ("comments", "author_id"),
            ("encryption_keys", "user_id"),
            ("sessions", "user_id"),
            ("requests", "user_id"),
            ("checkins", "user_id"),
        ]:
            assert (
                db.execute(
                    f"SELECT count(*) FROM {table} WHERE {field}=?", (a["userID"],)
                ).fetchone()[0]
                == 0
            )
        assert (
            db.execute("SELECT text FROM messages").fetchone()[0] == "KEEP MY MESSAGE"
        )
        report = db.execute("SELECT * FROM reports").fetchone()
        assert (
            report["evidence"] == report["review_note"] == ""
            and report["reason"] == "Account deleted"
        )
    companion = state(client, hb)
    garden = companion["connections"][0]
    assert (
        garden["endedAt"] is not None
        and garden["serverTotalDays"] == 1
        and garden["bestStreak"] == 1
    )
    assert next(p for p in companion["profiles"] if p["id"] == a["userID"])["age"] == 0
    assert (
        client.post(
            "/v1/auth/login", json=dict(username="alice", password=PASSWORD)
        ).status_code
        == 401
    )
    from dearly.moderation import set_role, set_suspended, verify_age
    from localization import RequestError

    with app.state.database.connect(write=True) as db:
        deleted_user = db.execute(
            "SELECT * FROM users WHERE id=?", (a["userID"],)
        ).fetchone()
        for restore in [
            lambda: set_suspended(db, deleted_user, False, "server-cli", "Restore", 1),
            lambda: set_role(db, deleted_user, "moderator", "server-cli", "Restore", 1),
            lambda: verify_age(
                db, deleted_user, "2000-01-01", "server-cli", "Restore", 1
            ),
        ]:
            with pytest.raises(RequestError) as denied:
                restore()
            assert denied.value.status_code == 409


def test_last_admin_cannot_delete_until_another_active_admin_exists(env):
    client, _, _ = env
    a, ha = register(env, "alice")
    b, _ = register(env, "bravo")
    grant(env, a["userID"], "admin")
    payload = dict(password=PASSWORD, confirmation="DELETE")
    assert (
        client.post("/v1/account/delete", headers=ha, json=payload).status_code == 409
    )
    grant(env, b["userID"], "admin")
    assert (
        client.post("/v1/account/delete", headers=ha, json=payload).status_code == 200
    )


@pytest.mark.parametrize(
    "path", ["account/export", "account/delete", "encryption/identity"]
)
def test_privacy_endpoints_reject_cross_origin_and_unauthenticated_requests(env, path):
    client, _, _ = env
    assert client.post("/v1/" + path, json={}).status_code in (401, 422)
    response = client.post(
        "/v1/auth/register",
        headers={"X-Dearly-Client": "web"},
        json=dict(
            username="browser",
            password=PASSWORD,
            nickname="Browser",
            birthDate="2000-01-01",
        ),
    )
    assert response.status_code == 201
    assert (
        client.post(
            "/v1/" + path,
            headers={"Origin": "https://evil.example", "X-Dearly-Client": "web"},
            json=dict(password=PASSWORD, confirmation="DELETE"),
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/" + path, json=dict(password=PASSWORD, confirmation="DELETE")
        ).status_code
        == 403
    )


def test_shared_interoperability_fixture_can_be_read_by_independent_python_consumer():
    fixture = json.loads(
        (
            Path(__file__).resolve().parents[2] / "web/src/fixtures/encryption-v1.json"
        ).read_text()
    )
    assert (
        open_content(fixture["alice"], fixture["alice"], fixture["journal"])
        == fixture["journalContent"]
    )
    assert (
        open_content(fixture["bob"], fixture["alice"], fixture["message"])
        == fixture["textContent"]
    )


def test_maximum_unicode_journal_and_socket_message_fit_ciphertext_transport(env):
    client, _, _ = env
    a, ha, b, hb, cid = pair(env)
    alice = identity(a["userID"])
    bob = identity(b["userID"], 31)
    publish(client, ha, alice)
    publish(client, hb, bob)
    jid, mid = str(uuid.uuid4()).upper(), str(uuid.uuid4()).upper()
    body = "🌱" * 20000
    wire = seal(alice, [alice], "journal", jid, "", {"title": "Unicode", "body": body})
    action(
        client,
        ha,
        "journal.save",
        dict(clientID=jid, title="", body=wire, audience="community", sharedText=body),
    )
    message = seal(alice, [alice, bob], "message", mid, cid, {"text": "🌱" * 4000})
    with client.websocket_connect("/ws/chat") as socket:
        socket_auth(socket, a["token"])
        socket.send_json(
            dict(
                type="message.send",
                requestID=str(uuid.uuid4()),
                clientID=mid,
                connectionID=cid,
                text=message,
            )
        )
        assert receive_type(socket, "ack")["result"]["id"] == mid


@pytest.mark.parametrize(
    "bad",
    ["null", "[]", "1", "{}", '{"v":NaN}', '{"v":1,"v":1}', "[" * 1200 + "]" * 1200],
)
def test_malformed_envelopes_are_bounded_and_never_raise_server_errors(env, bad):
    client, app, _ = env
    _, headers = register(env, "malformed")
    action(
        client,
        headers,
        "journal.save",
        dict(clientID=str(uuid.uuid4()), body=PREFIX + bad),
        expected=400,
    )
    with app.state.database.connect() as db:
        assert db.execute("SELECT count(*) FROM journals").fetchone()[0] == 0
