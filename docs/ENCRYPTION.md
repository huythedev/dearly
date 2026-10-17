# Encryption, recovery, and your data

## Save your recovery code

After signing in to an updated client, Dearly creates encryption keys on that device. On web, open **Settings → Encryption & recovery**. On iOS, open your avatar, then **Privacy & data**. Choose **Show recovery code**, store it in a password manager or another safe place, then choose **I saved my recovery code**.

The code starts with `DEARLY1-`. Someone with the code and your encrypted backup can read that backup. Staff cannot retrieve or reset a lost code. Save it before clearing website data or changing devices. Logout clears active decrypted content and keeps local keys for your next login.

On a new browser or iPhone, sign in to the same account/server, enter the code in these settings, and choose **Unlock encryption**. Locked entries cannot be edited; community features remain available. An incorrect code never replaces existing keys. Both companions must sign in with an updated client to create their keys before encrypted chat or companion sharing works.

## What is encrypted

| Content | Who can decrypt new content |
|---|---|
| Full journal title and body, for every audience | The author |
| Passage shared with a companion | Both members of that connection |
| Direct message | Both members of that connection |
| Published community passage and responses | Readable by the server and authorized community readers |
| Profile, birthday, matching, garden/check-ins, reports and routing metadata | Server-managed; not E2EE |

Private titles are inside the journal ciphertext; the server's public title field is empty. Anonymous community responses omit private ciphertext because its sender metadata identifies the author. Moderation covers public passages and reports, without decrypting private journal bodies or direct messages.

Old rows and backups are **not retroactively encrypted**. An older journal becomes encrypted when edited and saved with an updated client; historical plaintext messages stay plaintext. Use current clients on every device: older clients cannot display the ciphertext. Browser encryption needs HTTPS, except trusted loopback addresses such as `http://localhost:8003`. A phone using an HTTP LAN IP needs the HTTPS hostname.

## Verify a companion

Under **Verify encryption keys**, compare both fingerprints through another trusted channel. A fingerprint is SHA-256 of the account's two public keys. Clients remember the first key seen for each companion and refuse a different key later. Published identities are immutable in this version.

The first lookup trusts the server unless you compare fingerprints. The server also delivers browser code. A compromised device/server, malicious web code, stolen recovery code or recipient who copies plaintext can defeat confidentiality. This custom versioned format uses platform cryptographic primitives and automated cross-platform tests; it has **not received an independent cryptographic audit**. It has no Double Ratchet, per-message forward secrecy, post-compromise recovery or key rotation. Obtain an independent protocol review before treating Dearly as a high-assurance secure messenger.

## Download your data

Choose **Download my data**, enter your current password, and save the JSON file. It includes your profile, all your journals and sent messages, authored comments, connection/garden history, check-ins, invitations, blocks, hidden-story choices, listening reactions, and submitted reports. It excludes another person's private journal/authored message text, credentials, sessions, internal replay logs, and the real identity behind an anonymous story you reported.

When unlocked, **Decrypt content on this device** adds locally decrypted text. This produces a sensitive readable file. `encryptedOriginal` preserves original records, including any that fail to decrypt. Turn the option off to retain ciphertext. The file includes public keys and an encrypted private-key backup, never your recovery code or unwrapped private keys. Keep your code separately. This release has no archive-import screen.

## Delete your account

Choose **Delete my account**, enter your current password, type `DELETE`, and confirm. This removes live identifying profile fields, journals, sent messages, authored comments, check-ins, invitations, blocks, encryption identity, replay records and all server sessions. Sockets lose authorization. The current device removes its saved identity; clear other devices' local website/app data separately.

Connections end. A minimal **Deleted account** marker preserves the other person's garden rewards. Their messages and check-ins remain theirs. Relevant report evidence/text and linked audit notes are redacted; minimal report status and operator audit event IDs/actions remain. The last active administrator must appoint another before deleting their account.

Deletion cannot remove screenshots, previous downloads or independent copies. Operators must apply their backup retention policy: backups/WAL and older exports can retain earlier data. Reapply subsequent deletions before restoring an old backup to service. This endpoint does not promise physical secure erasure of storage media.

## Wire format v1

Implementations: `web/src/crypto.ts`, `ios/Dearly/Core/EndToEndCrypto.swift`; validation: `backend/dearly/encryption.py`. Independent PyCA vectors in `web/src/fixtures/encryption-v1.json` include Unicode. Their fixed keys/nonces are **test data only**; production uses secure randomness.

Accounts have separate P-256 ECDH and P-256 ECDSA keypairs. Public keys are uncompressed 65-byte X9.63 points. `fingerprint = hex(SHA256(agreementPublic || signingPublic))`, lowercase hex. The two 32-byte private scalars are concatenated and encrypted by AES-256-GCM under a random 32-byte recovery key, with a separate 12-byte nonce and UTF-8 AAD `dearly.identity.v1:USER_UUID`. `wrappedPrivate` is ciphertext followed by the 16-byte tag. The code is `DEARLY1-` plus unpadded base64url of the recovery key. UUIDs are canonical uppercase strings.

Content is `dearly:e2ee:1:` plus a JSON object: `v` (integer 1), `purpose` (`journal`, `passage`, `message`), `id`, `senderID`, `connectionID` (empty for full journals), `senderKeyID`, `nonce`, `ciphertext`, `ephemeralKey`, `salt`, `recipients`, `signature`. Binary fields use canonical unpadded base64url. The server rejects unknown/duplicate fields, invalid curves/sizes, wrong contexts, recipients or signatures.

Each record uses a fresh random 32-byte AES key and 12-byte nonce. JSON plaintext is `{title,body}` for journals and `{text}` for passages/messages. Content AAD (`CONTEXT`) is:

```text
dearly.e2ee.v1|PURPOSE|ID|SENDER_UUID|CONNECTION_UUID_OR_EMPTY
```

The record has a fresh ephemeral P-256 ECDH key. For each recipient, ECDH(ephemeralPrivate, recipientPublic) feeds HKDF-SHA256: fresh random 32-byte record salt, 32-byte output, info `dearly.wrap.v1|CONTEXT|RECIPIENT_UUID|RECIPIENT_FINGERPRINT`. AES-256-GCM wraps the record key using a fresh 12-byte nonce and AAD `CONTEXT|RECIPIENT_UUID|RECIPIENT_FINGERPRINT`. Recipient fields are `userID`, `keyID`, `nonce`, `wrappedKey` (48 bytes with tag). A full journal has only its author; passages/messages have exactly both current connection members.

ECDSA-SHA256 signs these UTF-8 lines, without a trailing newline: `dearly.e2ee.v1`, `purpose`, `id`, `senderID`, `connectionID`, `senderKeyID`, `nonce`, `ciphertext`, `ephemeralKey`, `salt`, then each recipient sorted lexicographically by uppercase `userID`. Recipient lines are `userID|keyID|nonce|wrappedKey`. Signatures are raw 64-byte `r || s`, not DER. Clients repeat signature/context checks and AES authentication; the server can verify bindings but cannot decrypt.

Web uses origin/account-scoped IndexedDB with non-extractable ECDH/signing CryptoKeys and an exportable recovery AES key. iOS uses a separate server/account-scoped Keychain service with `WhenUnlockedThisDeviceOnly`. These choices do not protect against malicious application code with the account's privileges.
