"""Independent PyCA producer/consumer for the web/CryptoKit wire-contract tests.

Fixed keys/nonces are TEST VECTORS ONLY. Production clients use secure randomness.
Run this file to regenerate web/src/fixtures/encryption-v1.json.
"""

import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

PREFIX = "dearly:e2ee:1:"


def b64(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def public(key):
    return key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def identity(uid, scalar=1):
    agreement = ec.derive_private_key(scalar, ec.SECP256R1())
    signing = ec.derive_private_key(scalar + 1, ec.SECP256R1())
    recovery = hashlib.sha256(("test-recovery-" + uid).encode()).digest()
    nonce = bytes(range(12))
    raw = scalar.to_bytes(32, "big") + (scalar + 1).to_bytes(32, "big")
    bundle = dict(
        userID=uid,
        agreementKey=b64(public(agreement)),
        signingKey=b64(public(signing)),
        fingerprint=hashlib.sha256(public(agreement) + public(signing)).hexdigest(),
        nonce=b64(nonce),
        wrappedPrivate=b64(
            AESGCM(recovery).encrypt(nonce, raw, ("dearly.identity.v1:" + uid).encode())
        ),
    )
    return dict(
        bundle=bundle, recoveryCode="DEARLY1-" + b64(recovery), privateBytes=b64(raw)
    )


def signed_fields(e):
    names = [
        "purpose",
        "id",
        "senderID",
        "connectionID",
        "senderKeyID",
        "nonce",
        "ciphertext",
        "ephemeralKey",
        "salt",
    ]
    recipients = [
        "|".join(r[k] for k in ["userID", "keyID", "nonce", "wrappedKey"])
        for r in sorted(e["recipients"], key=lambda r: r["userID"])
    ]
    return "\n".join(["dearly.e2ee.v1", *[e[n] for n in names], *recipients]).encode()


def seal(sender, recipients, purpose, rid, connection, plaintext):
    ephemeral = ec.derive_private_key(101, ec.SECP256R1())
    data_key = bytes(range(32))
    e = dict(
        v=1,
        purpose=purpose,
        id=rid,
        senderID=sender["bundle"]["userID"],
        connectionID=connection,
        senderKeyID=sender["bundle"]["fingerprint"],
        nonce=b64(bytes(range(12))),
        ciphertext="",
        ephemeralKey=b64(public(ephemeral)),
        salt=b64(bytes(range(32, 64))),
        recipients=[],
        signature="",
    )
    context = "|".join(["dearly.e2ee.v1", purpose, rid, e["senderID"], connection])
    e["ciphertext"] = b64(
        AESGCM(data_key).encrypt(
            unb64(e["nonce"]),
            json.dumps(plaintext, ensure_ascii=False, separators=(",", ":")).encode(),
            context.encode(),
        )
    )
    for index, recipient in enumerate(recipients):
        r = dict(
            userID=recipient["bundle"]["userID"],
            keyID=recipient["bundle"]["fingerprint"],
            nonce=b64(bytes([index + 50]) * 12),
            wrappedKey="",
        )
        aad = (context + "|" + r["userID"] + "|" + r["keyID"]).encode()
        pub = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), unb64(recipient["bundle"]["agreementKey"])
        )
        shared = ephemeral.exchange(ec.ECDH(), pub)
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=unb64(e["salt"]),
            info=b"dearly.wrap.v1|" + aad,
        ).derive(shared)
        r["wrappedKey"] = b64(AESGCM(key).encrypt(unb64(r["nonce"]), data_key, aad))
        e["recipients"].append(r)
    scalar = int.from_bytes(unb64(sender["privateBytes"])[32:], "big")
    signature = ec.derive_private_key(scalar, ec.SECP256R1()).sign(
        signed_fields(e), ec.ECDSA(hashes.SHA256())
    )
    r, s = utils.decode_dss_signature(signature)
    e["signature"] = b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return PREFIX + json.dumps(e, separators=(",", ":"))


def open_content(receiver, sender, wire):
    e = json.loads(wire[len(PREFIX) :])
    signature = unb64(e["signature"])
    pub = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), unb64(sender["bundle"]["signingKey"])
    )
    pub.verify(
        utils.encode_dss_signature(
            int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
        ),
        signed_fields(e),
        ec.ECDSA(hashes.SHA256()),
    )
    context = "|".join(
        ["dearly.e2ee.v1", e["purpose"], e["id"], e["senderID"], e["connectionID"]]
    )
    r = next(r for r in e["recipients"] if r["userID"] == receiver["bundle"]["userID"])
    aad = (context + "|" + r["userID"] + "|" + r["keyID"]).encode()
    private = ec.derive_private_key(
        int.from_bytes(unb64(receiver["privateBytes"])[:32], "big"), ec.SECP256R1()
    )
    ephemeral = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), unb64(e["ephemeralKey"])
    )
    shared = private.exchange(ec.ECDH(), ephemeral)
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=unb64(e["salt"]),
        info=b"dearly.wrap.v1|" + aad,
    ).derive(shared)
    content_key = AESGCM(key).decrypt(unb64(r["nonce"]), unb64(r["wrappedKey"]), aad)
    return json.loads(
        AESGCM(content_key).decrypt(
            unb64(e["nonce"]), unb64(e["ciphertext"]), context.encode()
        )
    )


if __name__ == "__main__":
    a = identity("A0000000-0000-4000-8000-000000000001")
    b = identity("B0000000-0000-4000-8000-000000000002", 31)
    cid = "C0000000-0000-4000-8000-000000000003"
    jid = "D0000000-0000-4000-8000-000000000004"
    mid = "E0000000-0000-4000-8000-000000000005"
    journal = dict(
        title="Một ngày mới 🌱", body="Nội dung riêng tư. A quiet thought. 🔐"
    )
    text = dict(text="Mình ở đây, cùng bạn. 🌿")
    fixture = dict(
        alice=a,
        bob=b,
        connectionID=cid,
        journalID=jid,
        messageID=mid,
        journalContent=journal,
        textContent=text,
        journal=seal(a, [a], "journal", jid, "", journal),
        passage=seal(a, [a, b], "passage", jid, cid, text),
        message=seal(a, [a, b], "message", mid, cid, text),
    )
    path = Path(__file__).resolve().parents[2] / "web/src/fixtures/encryption-v1.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n")
