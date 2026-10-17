# Management access audit — 17 October 2026

[Security behavior](SECURITY.md) · [Administration](ADMINISTRATION.md) · [API contract](API.md)

The review started from commit `e658cb9` after a report that Management appeared public. It covered FastAPI/production frontend routing, browser and iOS permission checks, staff reads and mutations, role changes, browser history, and retained screen data.

The existing staff APIs already rejected anonymous requests with 401 and ordinary members with 403. The review did not reproduce an unauthenticated staff-data read or mutation. The document route and client state handling needed additional protection; a public SPA document alone did not establish that staff records had been exposed.

## Findings and fixes

| Finding | Previous behavior | Fix |
|---|---|---|
| Management HTML followed the public SPA fallback | `/management` returned the app document before authorization | FastAPI checks the current session before serving it; the separate Nginx frontend uses an internal authorization subrequest. Guests get 401, members get 403, and failures stay blocked. Protected documents are not cached. |
| UI checks accepted permission strings without validating the role | A member, legacy, or unknown-role snapshot carrying stale staff grants could show Management | Shared web and native checks require an explicit grant within the recognized role's maximum permissions. Missing/unknown roles deny access. |
| Management opened using a cached snapshot | A stale staff session could display controls before a server rejection | Web checks current staff authorization before mounting controls or reading lists; iOS forces a fresh authenticated snapshot on entry/foreground. Browser history restoration also rechecks access. |
| Role changes did not reset every open form | An admin's already-open role form could survive a demotion to moderator | Web resets the console when effective permissions change; iOS clears pending confirmations and checks permission again before sending a staff command. |
| Staff reads did not identify the originating browser account; denied pagination could retain records | A shared cookie could change accounts, and already-loaded rows could remain after a forbidden request or failed snapshot refresh | Web staff reads include `X-Dearly-User`; the backend rejects mismatches. Denials discard rows and close the console/dialogs immediately, independently of snapshot refresh success. Native staff denials also clear cached grants. |

## Regression coverage

- Backend tests cover protected documents (including subpaths and cookies), guest/member rejection, current database roles, forged role headers, account mismatches, suspended/revoked sessions, and the existing action authorization/idempotency checks.
- Web unit tests cover missing, malformed, unknown, and excessive permission claims.
- Desktop/mobile browser tests cover direct unauthorized requests, stale grants, waiting for authorization, wrong-account responses, demotion with an open form, rejected pagination/actions during a failed sync, browser history restoration, and moderator/admin age review.
- Docker smoke tests exercise guest/member/staff document access, live role revocation, cookies, the internal-only authorization location, separate custom ports, and backend host retargeting.
- Native tests verify role/grant limits; the iPhone simulator CI job builds and tests the native changes.

This is a source and disposable-environment audit. It does not inspect production account roles, access logs, or historical access. It does not establish that a production data disclosure occurred. Existing journals, accounts, role assignments, and sessions require no migration for these fixes.

## Install the update

Pull the updated `main`, then rebuild both services from the repository root:

```bash
docker compose up -d --build frontend backend
```

The new frontend authorization check requires the updated backend. Rebuild the iOS app to include its additional client-side role checks and confirmation cleanup. Server-side authorization applies to existing clients on every request.
