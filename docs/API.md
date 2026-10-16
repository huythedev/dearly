# API contract v0.5

The base URL is the server origin, without a path or query. All `/v1/*` endpoints except register/login require `Authorization: Bearer TOKEN`. The running server exposes the full OpenAPI specification at `/docs`.

The web client uses the frontend origin with relative `/v1/...` paths. In split Docker deployments, Nginx forwards these requests and `/ws/chat` to the configured `DEARLY_BACKEND_ADDRESS`, preserving public Host/port, Origin and cookies. It opts into an HttpOnly session cookie by sending `X-Dearly-Client: web` on register/login. This response omits `token` while keeping `userID` / `expiresAt`; native bearer responses are unchanged. Cookie-authenticated unsafe requests require that header and a matching Origin/Host. Browser logout clears/revokes the cookie session. HTTPS web cookies use Secure; all use SameSite=Strict. No CORS configuration is needed.

| Method / path | Input | Output |
|---|---|---|
| GET `/health` | No authentication | status, version, dayBoundary UTC |
| POST `/v1/auth/register` | username, password, nickname, birthDate YYYY-MM-DD | token, userID, expiresAt |
| POST `/v1/auth/login` | username, password | token, userID, expiresAt |
| POST `/v1/auth/logout` | Bearer token | ok; revokes the current token |
| GET `/v1/state` | Bearer; optional If-None-Match | `{state, serverNow}` + ETag, or 304 without a body |
| POST `/v1/actions` | requestID UUID, kind, payload | ok; id for creation actions |
| GET `/v1/messages` | connectionID, optional before ID, limit 1–100 | items in ascending time order, nextCursor |
| GET `/v1/journals` | optional before ID, limit 1–60 | Own journals in descending time order, nextCursor |
| GET `/v1/connections` | optional before ID, limit 1–50 (default 20) | Own saved gardens; items, profiles, nextCursor |
| GET `/v1/staff/reports` | status open/reviewed/dismissed (default open), before UUID, limit 1–50 | Report page; requires reports.read |
| GET `/v1/staff/users` | q: username/nickname prefix, before UUID, limit 1–50 | Account page; requires users.read |
| GET `/v1/staff/audit` | before: integer event ID, limit 1–50 | Audit page; requires audit.read |

JSON dates are **seconds since 2001-01-01 UTC**, matching the default Swift JSONEncoder/JSONDecoder Date representation. Native DTOs do not use the Unix epoch. `birthDate` is a Gregorian date string rather than a timestamp. IDs are UUIDs. Check-in days use YYYY-MM-DD in server UTC.

## WebSocket chat

Connect to `/ws/chat` using the origin's `ws:` or `wss:` scheme. A browser must send a matching Origin and its HttpOnly cookie. Native clients may omit Origin and send a bearer token in the first frame. Do not put a token in a URL/query string. Within 5 seconds, send:

```json
{"type":"authenticate"}
```

For a native client, add `"token":"TOKEN"` to that frame. Success replies with `{"type":"ready","userID":"UUID"}`. Then send:

```json
{"type":"message.send","requestID":"B9438240-7D2B-49A3-83EE-4B68543D34E6","connectionID":"439903D4-52BE-454D-9F02-BF068F88F39F","text":"Hello"}
```

| type | Fields / behavior |
|---|---|
| `ack` | `requestID`, `result: {ok, id}` after commit |
| `message` | `message` with the existing chat DTO, authorized for the current active connection |
| `state.changed` | Invalidation only; fetch `/v1/state` to reconcile other changes or an overflowed queue |
| `error` | `requestID`, HTTP-like `status`, English `detail`; invalid input does not mutate |
| `ping` / `pong` | Keepalive; respond to server ping with `{type: "ping"}` |

REST `/v1/actions` and socket sends share authorization, validation, rate limits, transactions, and the request-ID store. Retry the same UUID/payload through either transport after a lost reply. Socket sends cannot execute staff/profile/journal actions. Event delivery rechecks sessions, suspension, active membership, and age eligibility. Revoked/expired sessions close with 4401, disallowed origins with 4403, excess sessions with 4429, malformed frames with 1008, oversized messages with 1009, and temporary database failures with 1013. Idle sessions are rechecked within 15 seconds, including CLI changes. There are at most 32 sockets globally, 4 per account, and 32 queued events per socket. Uvicorn/wsproto bounds assembled frames to 16 KiB; the app also checks complete frames. Use the documented single worker.

## Actions

Each action POST has this form:

```json
{
  "requestID": "B9438240-7D2B-49A3-83EE-4B68543D34E6",
  "kind": "message.send",
  "payload": {
    "connectionID": "439903D4-52BE-454D-9F02-BF068F88F39F",
    "text": "I am still here today."
  }
}
```

| kind | payload |
|---|---|
| journal.save | id when editing; title, body, sharedText, audience, anonymous, commentsEnabled, support |
| journal.delete | id |
| journal.hide | community post id; hides only that post for the current user |
| journal.listen | id, enabled bool (sets a state rather than toggling blindly) |
| journal.comment | id, text |
| invitation.send | userID **or** journalID of an identified public post; anonymous posts return 403 |
| invitation.accept / invitation.dismiss | invitation id |
| message.send | connectionID, text |
| connection.checkin / connection.leave | connectionID |
| connection.pause | connectionID, paused bool |
| user.block | userID or identified journalID; legacy anonymous journalID requests hide only that post |
| report.create | userID or journalID, reason |
| profile.update | nickname, bio, interests (at most 8), support, pace |
| staff.report.review | report id, status open/reviewed/dismissed, reason; requires reports.review |
| staff.report.hide | report id, reason; requires reports.hide |
| staff.report.restore | report id, reason; requires reports.hide; allows sharing without publishing automatically |
| staff.user.suspend | userID, suspended bool, reason; requires users.suspend |
| staff.user.verify_age | userID, birthDate YYYY-MM-DD, reason; requires users.verify_age |
| staff.user.role | userID, role user/moderator, reason; requires roles.manage |

`audience`: `privateOnly` / `companion` / `community`. `support`: `listen` / `relate` / `brainstorm`. Support identifiers are independent of display language. Legacy Vietnamese support inputs are accepted and normalized; responses use canonical English identifiers. The new iOS app can also decode older Vietnamese responses. Upgrade the app and backend together because older apps cannot decode the new identifiers. Journal creation uses a server-issued ID; edits require an existing journal owned by the current user.

Reuse `requestID` when retrying the same mutation. The server stores the result and payload hash atomically for 7 days; reusing an ID with a different payload returns 409. Check-ins also have a unique `(connection, day, user)` constraint independent of retry keys. The server does not accept client-declared days, streaks, rewards, or members.

## Staff roles and payloads

`state.currentUserRole` is `user`, `moderator`, or `admin`; `state.permissions` contains only the current account's permission strings. Roles are never accepted from registration or public profile updates. Older state payloads omit these fields; the iOS app treats that as no staff access. The personal snapshot format remains `schemaVersion=1`; SQLite storage migrates separately to `user_version=4`.

Moderators have `reports.read`, `reports.review`, and `reports.hide`. Admins additionally have `users.read`, `users.suspend`, `users.verify_age`, `roles.manage`, and `audit.read`. Every staff read/write is authenticated and authorized server-side using the current database role, including idempotent retries after demotion. Regular users receive 403. Staff mutations reject unknown payload keys and require a non-empty reason of at most 1,000 characters.

The API cannot grant `admin`, modify an existing admin account, or let an admin modify their own account. Use the backend `set-role`, `verify-age`, `suspend`, or `restore` commands for admin accounts. The last active admin is protected from demotion/suspension.

Staff pages return `{items, nextCursor}` with 30 records by default and at most 50. Report/account cursors are UUIDs ordered by `(created,id)` descending; audit cursors are integer event IDs descending. Responses use `Cache-Control: no-store` and `Vary: Authorization`.

- Report: `id`, `reporterID`, `reportedID`, `reporterNickname`, `reportedNickname`, `reason`, `status`, `date`, optional `journalID`, `evidence`, `canHide`, `canRestore`, `reviewNote`, optional `reviewerID` and `reviewedAt`. `reviewerID` is an account UUID string or `server-cli`. Evidence is the reported public excerpt, never the author's full/private body. Legacy/account-only reports have empty evidence and no journal ID. Deleting a source post nulls its journal ID but retains the evidence. `canHide` is true only while that reported post still exists publicly under the reported author. `canRestore` indicates a durable sharing restriction. Report cursors continue working when their source report changes status.
- Account: `id`, `username`, `nickname`, `role`, `suspended`, `ageVerified`, `birthDate`. This endpoint is admin-only and never returns password hashes or sessions.
- Audit: integer `id`, `actorID` (UUID string or `server-cli`), `actorName`, `action`, `targetID`, `detail`, `date`. Details contain the reason/note and relevant status or before/after role, not birth dates or credentials.

`staff.report.hide` changes the reported community post to private, removes its comments/listening reactions, and creates a durable sharing restriction. The author receives `moderationHidden: true`, keeps the full journal, and can save private edits; attempts to share to community or companion return 403 until `staff.report.restore`. Restoration is audited and leaves the entry private. Missing/deleted/already-private posts return 409 for hide. `staff.user.suspend` revokes all sessions and ends connections without removing rewards. Suspended accounts' comments and posts are omitted from public reads. Restoring access requires a new login and does not reopen connections. Correcting a birth date also ends connections and pending invitations for eligibility re-checking; confirming the same date preserves them. Successful staff and operator mutations append audit events in the same transaction.

## DTO privacy

- Only the journal owner receives its original title/body; others receive only the selected `sharedText`, with empty body/title.
- Anonymous posts use the post UUID as the authorID alias in other users' DTOs. The real author ID does not appear in the post or the author's replies.
- Anonymous posts reject invitations and always have `canInviteAuthor: false`. Profile invitations still require compatible age groups, verified ages, and mutual consent. The v3 migration removes old pending anonymous invitations.
- `journal.hide` hides only a post UUID without blocking an account, changing suggestions, or ending connections. Blocking an identified account does not remove anonymous posts/replies, which would create an identity probe. Hide or report anonymous content instead. Authors may still reveal their identity through what they write.
- Companion journals belong to a specific connection ID; ended connections and new companions cannot read them.
- Snapshots include only profiles/records needed by the current user, rather than global users/sessions/reports tables. `suggestedUserIDs` contains only accounts checked for connection eligibility. Separate staff endpoints enforce the permissions above.
- Public profiles contain current age and verification status, without birth dates, usernames, passwords, or tokens.
- Chat history is available only to members of an active connection. Old gardens return summaries without old chat transcripts.

## Errors and limits

Errors use `{ "detail": "message" }` with English source text by default. `Accept-Language: vi` selects Vietnamese translations, including parameterized validation and upload-limit errors. Responses include `Content-Language`, `Vary: Accept-Language`, and `Cache-Control: no-store`. Successful DTO identifiers and user-written content do not change with language. Validation does not reflect passwords. See [localization](LOCALIZATION.md).

401: log in again. 403: permission or age-group restriction. 404: missing/hidden record. 408: body upload timeout; connection closes. 409: state conflict. 413: request too large. 429: rate limit or too many active uploads. 503: database busy, with Retry-After. Invalid `support` types return 400 rather than 500.

State has no global cursor; it is a snapshot of the bounded windows in the backend README. Personal journals, chat, and saved gardens have separate pagination endpoints with `Cache-Control: no-store`. Saved gardens use descending `(started,id)` order and include only member profiles for that page. State always includes the active connection, even if an old archive has an incorrect timestamp. Mutations and UTC day changes update the ETag; it contains no token and differs between accounts. The app never uploads its state to overwrite the database.
