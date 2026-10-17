"""Validate signed client ciphertext. This module never receives decryption keys.

The interoperable wire format is specified in docs/ENCRYPTION.md. Authorization
and resource binding are still checked even though content is opaque to us.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from fastapi import Header, Response
from pydantic import BaseModel, ConfigDict, Field

from .database import changed
from .validation import fail, identifier

PREFIX = "dearly:e2ee:1:"


def decode(value, minimum, maximum=None):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        fail("Invalid encrypted data.")
    if len(value) > ((maximum or minimum) * 4 + 2) // 3:
        fail("Invalid encrypted data.")
    try:
        data = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError):
        fail("Invalid encrypted data.")
    if not minimum <= len(data) <= (maximum or minimum) or encode(data) != value:
        fail("Invalid encrypted data.")
    return data


def encode(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def point(value):
    data = decode(value, 65)
    if data[0] != 4:
        fail("Invalid encryption key.")
    try:
        return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), data)
    except ValueError:
        fail("Invalid encryption key.")


def key_dto(row, private=False):
    value = dict(
        userID=row["user_id"],
        agreementKey=row["agreement_key"],
        signingKey=row["signing_key"],
        fingerprint=row["fingerprint"],
    )
    if private:
        value.update(wrappedPrivate=row["wrapped_private"], nonce=row["nonce"])
    return value


def key_for(db, uid):
    return db.execute(
        "SELECT * FROM encryption_keys WHERE user_id=?", (uid,)
    ).fetchone()


def signature_input(e):
    return "\n".join(
        [
            "dearly.e2ee.v1",
            e["purpose"],
            e["id"],
            e["senderID"],
            e["connectionID"],
            e["senderKeyID"],
            e["nonce"],
            e["ciphertext"],
            e["ephemeralKey"],
            e["salt"],
            *[
                "|".join((r["userID"], r["keyID"], r["nonce"], r["wrappedKey"]))
                for r in sorted(e["recipients"], key=lambda r: r["userID"])
            ],
        ]
    ).encode("ascii")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("Duplicate field in encrypted data.")
        result[key] = value
    return result


def validate_content(db, value, *, purpose, resource, sender, members, connection=""):
    """Check a bounded, signed envelope and forbid downgrades for enabled users."""
    if not isinstance(value, str) or len(value) > 180000:
        fail("Invalid encrypted data.")
    if not value.startswith(PREFIX):
        if value.startswith("dearly:e2ee:"):
            fail("This encryption version is not supported. Update your app.", 409)
        if any(key_for(db, member) for member in members):
            fail("End-to-end encryption is required. Update or unlock your app.", 409)
        return False
    try:
        e = json.loads(value[len(PREFIX) :], object_pairs_hook=unique_object)
    except (ValueError, RecursionError):
        fail("Invalid encrypted data.")
    fields = {
        "v",
        "purpose",
        "id",
        "senderID",
        "connectionID",
        "senderKeyID",
        "nonce",
        "ciphertext",
        "ephemeralKey",
        "salt",
        "recipients",
        "signature",
    }
    if (
        not isinstance(e, dict)
        or set(e) != fields
        or type(e["v"]) is not int
        or e["v"] != 1
    ):
        fail("Invalid encrypted data.")
    if (e["purpose"], e["id"], e["senderID"], e["connectionID"]) != (
        purpose,
        resource,
        sender,
        connection,
    ):
        fail("Encrypted content belongs to a different resource.")
    sender_key = key_for(db, sender)
    if sender_key is None or e["senderKeyID"] != sender_key["fingerprint"]:
        fail("Encryption key not found. Unlock encryption first.", 409)
    decode(e["nonce"], 12)
    decode(e["salt"], 32)
    decode(
        e["ciphertext"],
        17,
        100000 if purpose == "journal" else 81000 if purpose == "passage" else 17000,
    )
    point(e["ephemeralKey"])
    recipients = e["recipients"]
    if not isinstance(recipients, list) or len(recipients) != len(members):
        fail("Invalid encrypted recipients.")
    ids = []
    for r in recipients:
        if not isinstance(r, dict) or set(r) != {
            "userID",
            "keyID",
            "nonce",
            "wrappedKey",
        }:
            fail("Invalid encrypted recipients.")
        if not isinstance(r["userID"], str) or r["userID"] not in members:
            fail("Invalid encrypted recipients.")
        key = key_for(db, r["userID"])
        if key is None or r["keyID"] != key["fingerprint"]:
            fail("Your companion must enable encryption in an updated app first.", 409)
        decode(r["nonce"], 12)
        decode(r["wrappedKey"], 48)
        ids.append(r["userID"])
    if len(set(ids)) != len(members):
        fail("Invalid encrypted recipients.")
    signature = decode(e["signature"], 64)
    der = utils.encode_dss_signature(
        int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
    )
    try:
        point(sender_key["signing_key"]).verify(
            der, signature_input(e), ec.ECDSA(hashes.SHA256())
        )
    except (InvalidSignature, ValueError, TypeError):
        fail("Encrypted content signature is invalid.")
    return True


class IdentityInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    agreementKey: str = Field(max_length=87)
    signingKey: str = Field(max_length=87)
    wrappedPrivate: str = Field(max_length=107)
    nonce: str = Field(max_length=16)


def register_routes(app, services):
    @app.get("/v1/encryption/identity")
    def own_identity(
        response: Response,
        authorization: str | None = Header(default=None),
        x_dearly_user: str | None = Header(default=None),
    ):
        response.headers.update(
            {"Cache-Control": "no-store", "Vary": "Cookie, Authorization"}
        )
        with services.database.connect() as db:
            user = services.account_user(db, authorization, x_dearly_user)
            row = key_for(db, user["id"])
            if row is None:
                fail("Encryption has not been enabled for this account.", 404)
            return key_dto(row, True)

    @app.post("/v1/encryption/identity")
    def publish_identity(
        data: IdentityInput,
        response: Response,
        authorization: str | None = Header(default=None),
        x_dearly_user: str | None = Header(default=None),
    ):
        response.headers.update(
            {"Cache-Control": "no-store", "Vary": "Cookie, Authorization"}
        )
        point(data.agreementKey)
        point(data.signingKey)
        decode(data.wrappedPrivate, 80)
        decode(data.nonce, 12)
        fingerprint = hashlib.sha256(
            decode(data.agreementKey, 65) + decode(data.signingKey, 65)
        ).hexdigest()
        with services.database.connect(write=True) as db:
            user = services.account_user(db, authorization, x_dearly_user)
            services.limiter.check("keys:" + user["id"], 10, 1 / 30)
            row = key_for(db, user["id"])
            expected = dict(
                userID=user["id"],
                agreementKey=data.agreementKey,
                signingKey=data.signingKey,
                fingerprint=fingerprint,
                wrappedPrivate=data.wrappedPrivate,
                nonce=data.nonce,
            )
            if row is not None:
                if key_dto(row, True) != expected:
                    fail(
                        "Encryption keys already exist. Use your recovery code on this device.",
                        409,
                    )
                return expected
            db.execute(
                "INSERT INTO encryption_keys VALUES(?,?,?,?,?,?,?)",
                (
                    user["id"],
                    data.agreementKey,
                    data.signingKey,
                    fingerprint,
                    data.wrappedPrivate,
                    data.nonce,
                    services.clock(),
                ),
            )
            changed(db)
        services.hub.publish()
        return expected

    @app.get("/v1/encryption/keys/{user_id}")
    def public_identity(
        user_id: str,
        response: Response,
        authorization: str | None = Header(default=None),
        x_dearly_user: str | None = Header(default=None),
    ):
        response.headers.update(
            {"Cache-Control": "no-store", "Vary": "Cookie, Authorization"}
        )
        target = identifier(user_id)
        with services.database.connect() as db:
            user = services.account_user(db, authorization, x_dearly_user)
            services.limiter.check("key-read:" + user["id"], 120, 2)
            if (
                target != user["id"]
                and not db.execute(
                    "SELECT 1 FROM connections WHERE (first_id=? AND second_id=?) OR (first_id=? AND second_id=?)",
                    (user["id"], target, target, user["id"]),
                ).fetchone()
            ):
                fail("Encryption key not found.", 404)
            row = key_for(db, target)
            if row is None:
                fail("Encryption key not found.", 404)
            return key_dto(row)
