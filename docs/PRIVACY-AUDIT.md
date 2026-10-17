# Privacy and security verification — 2026-10-17

## Scope

Gray-box adversarial testing on disposable SQLite databases, HTTP/TestClient requests, real loopback HTTP/WebSocket sessions and desktop/mobile WebKit browser flows. All accounts/content were synthetic. Production DNS, Cloudflare/origin settings, accounts, logs and backups were not accessed. This is a focused application assessment, not an independent penetration-test certification or cryptographic audit.

## Attacks and results

| Surface | Probes | Verified behavior |
|---|---|---|
| Authentication/Management | Guest/member access, stale grants, demotion, revocation, cross-account retries | Current server roles enforced; denied reads clear staff UI; switched-account writes return 409 |
| Ownership/anonymity | Foreign journal edits/archives, anonymous invitation/block probes, report export | Owner-only bodies; anonymous public DTOs omit real IDs and identifying ciphertext; exports omit reported-user IDs |
| CSRF/sessions | Foreign Origin, unsafe cookie requests without web header, logout/deletion | Same-origin/custom header required; deletion revokes every session and socket |
| E2EE key delivery | Unauthenticated/unrelated lookup, invalid P-256 point, overwrite, extra fields | Own wrapped identity stays private; related users receive public keys only; replacement rejected |
| E2EE content | Tampered signature/ciphertext/nonce/salt/ephemeral key/context; duplicate/missing/foreign/wrong-key recipients; resource replay; plaintext downgrade | Rejected without storing content; enabled accounts cannot send plaintext through legacy clients |
| Parsers/resources | Invalid types, null/array/scalar/duplicate/deeply nested envelopes, oversized frames/bodies, slow/incomplete upload | Controlled 4xx and rollback; existing upload deadlines/admission retained |
| Data download | Wrong password, switched account, foreign content, anonymous reports, credentials/replay records | Password/account binding; ownership-filtered no-store attachment; bounded-memory spool, two concurrent exports |
| Deletion | Wrong password/confirmation, all sessions, comments/report copies, foreign keys, final admin, garden rewards | Atomic erasure/redaction and revocation; pseudonymous garden summary retained; final admin protected |
| Recovery/transport | Wrong code/account, simultaneous first logins across tabs/devices, clean second-browser storage, persisted keys, Unicode, encrypted socket + identical REST retry + encrypted reply | Existing identity survives failed recovery; restored content reads correctly; retries do not duplicate writes |

## Changes made

- New sensitive writes use client E2EE. Keys are separate from login passwords and never sent unwrapped to the server. [ENCRYPTION.md](ENCRYPTION.md) specifies the format, fingerprint verification and trust limits.
- Added password-confirmed export/deletion. Export filters ownership and prevents report-based deanonymization. Deletion redacts relevant report/audit text and blocks staff restoration of deleted accounts.
- Serialized first identity creation in IndexedDB so simultaneous tabs publish one persisted key. A different device winning initialization opens recovery instead of replacing keys. Deleted-account tombstones cannot be reactivated through CLI/staff helpers or authenticated sessions.
- Preserved exact socket/REST payloads, including optional `clientID`, for idempotency. Legacy plaintext validation remains; encryption-enabled users reject downgrade writes.
- Raised HTTP bodies from 128 to 256 KiB and socket frames from 16 to 32 KiB for bounded UTF-8 ciphertext/base64 overhead. Timing/concurrency limits remain; Nginx/native/launcher sizes match.
- CI runs on PRs/manual dispatch and cancels superseded runs. Merging a tested PR no longer repeats the full suite. Direct pushes require a manual run.

No unauthenticated staff-data or cross-account plaintext bypass was reproduced in the existing authorization controls. These changes add requested privacy controls and protect their new boundaries; they are not evidence of a production breach.

## Reproduce

```bash
python -m pytest -q backend/tests
ruff check backend configure-docker.py --select F,E9
pip-audit -r backend/requirements.txt
npm --prefix web test
npm --prefix web run build
npm --prefix web audit
```

With browser binaries and a disposable backend, run `npm --prefix web run test:e2e`. Never set `DEARLY_E2E_BASE_URL` to production. Local verification reached **148 backend tests, 28 web unit tests and 60 WebKit desktop/mobile flows**, including real encrypted journal/export/delete requests. Advisory scans found no known dependency vulnerabilities at test time.

Required CI covers backend/lint/advisories, Chromium, split Docker/custom ports/retargeted backend, and iOS Simulator. The native suite adds four CryptoKit encryption/recovery/tampering tests to the existing 33. Python, Web Crypto and CryptoKit consume the independent Unicode fixture in `web/src/fixtures/encryption-v1.json`.

## Limits and operations

No forward secrecy, key rotation, independent protocol review, physical-iPhone validation, production TLS review/load test or external host/network scan is claimed. Old plaintext/backups are not silently migrated. Community/profile/routing metadata remain server-readable. Keep HTTPS, restrict origin access, protect backups and reapply deletions after restoring backups. Deploy the backend and both clients together; back up before schema v5 and save recovery codes.
