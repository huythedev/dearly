# Source audit — 16 October 2026

[All guides](README.md) · [Development](DEVELOPMENT.md) · [Security behavior](SECURITY.md)

This review covers the tracked runtime source for the FastAPI backend, React web client and SwiftUI iOS app, plus their Docker images, configuration helper, proxy configuration, Xcode settings, localization catalogs and CI/test harnesses. It started from commit `32ec2f9`. Tests use disposable accounts and databases; the public deployment was not exercised or changed.

## Findings and fixes

| Finding | Effect | Change and regression coverage |
|---|---|---|
| A browser retry could use a different account's shared cookie | A lost mutation reply followed by login in another tab could replay the write under that account | Web REST mutations send the originating `X-Dearly-User`. The backend compares it with the authenticated user inside the transaction and returns 409 before a write or idempotency record on mismatch. HTTP regression switches accounts before replay; web tests check that the header survives retry. |
| Snapshot reads could drop invalidations or overlap | WebSocket changes arriving during a read were discarded; concurrent forced reads on web could apply out of order | Web `RefreshQueue` and iOS `StateSynchronizer` serialize reads and coalesce invalidations into a forced follow-up. Unit tests exercise concurrency, cancellation and recovery; browser tests deliver an event during a held snapshot. |
| Obsolete asynchronous work could affect a new session or socket | Late callbacks/errors could update status or trigger a REST fallback after logout; a replaced iOS socket shared the account generation | Cancel web operations and snapshots on session changes, check generations before applying results, ignore callbacks from stopped sockets, and give native sockets a separate lifecycle ID. Socket tests cover late expiration and failed-send cleanup. Native page reads consistently handle expired sessions and reject stale results. |
| Pagination used React state as its request lock | Multiple same-frame clicks could start duplicate reads; superseded reads kept running and old related profiles were retained on reset | Use a synchronous request guard, abort replaced/unmounted reads and clear associated profiles. Browser regression dispatches two clicks in one frame. Native journal archive checks request identity/cancellation before applying results or errors. |
| System appearance changed without refreshing the web toggle | The theme changed but the toggle label/icon could still describe the previous appearance | Resolve the system color preference in the preferences context. Browser regression changes the emulated system theme and checks the button and document together. |
| Nginx's generic extension regex overrode the assets prefix | Fingerprinted JavaScript/CSS missed the intended seven-day cache policy | Use an ordered assets regex after the hidden-file rejection. The real-container smoke test checks a built asset's cache header and rejection of hidden assets. |
| Native local-network permission had an empty purpose string | The OS permission lacked an explanation of why Dearly contacts a LAN server | Fill both build configurations with the server-connection purpose. Native test checks the built app's value. Release still requires HTTPS. |
| Store mutations accepted unused local-update closures | Duplicate, unexecuted client rules obscured which state was authoritative | Remove the dead closures and temporary values. Mutations continue to use the backend response and serialized snapshot reconciliation. Existing domain-model tests remain alongside API contract tests. |

The account header is a consistency check, not an authentication credential. Existing bearer clients can omit it. A browser action that receives 409 is not retried automatically; reload to load the currently authenticated account before submitting again. An already committed write cannot be undone by cancelling its client request.

## Module boundaries

### Backend

`backend/server.py` remains the compatible factory/CLI import entrypoint. Implementation lives in `backend/dearly/`:

| Module | Responsibility |
|---|---|
| `application.py` | App assembly, middleware, exceptions, route registration and optional built-web mount |
| `database.py` | Schema, SQLite connections, migrations and revision counter |
| `constants.py`, `validation.py` | Shared identifiers, permissions, input models and validation |
| `policies.py` | Membership, blocking, eligibility and journal-read policy |
| `serialization.py` | Authorized personal/staff DTOs and bounded snapshots |
| `moderation.py` | Permission checks, audited staff operations and last-admin protection |
| `actions.py` | Transactional personal mutations |
| `service.py` | Per-app sessions, password hashing limits, authentication and shared idempotent execution |
| `limits.py` | Rate buckets and bounded request-body middleware |
| `routes_auth.py`, `routes_read.py`, `routes_staff.py`, `routes_chat.py` | HTTP and WebSocket transport handling by feature |

Dependencies run from routes through application services to domain policies/database helpers. HTTP and WebSocket writes use the same executor. No global database, limiter or event hub is shared across app instances. The Docker allowlist and COPY instructions include the package. Localization coverage scans all runtime Python modules so moving errors does not silently remove their checks.

### Web

`App.tsx` owns navigation and the authenticated shell. `Auth.tsx`, `Settings.tsx`, `PreferenceControls.tsx`, `Community.tsx` and `ReportDialog.tsx` own their respective screens/shared controls. Private journal editing no longer owns the report dialog used by chat.

`api.ts` owns same-origin HTTP, deadlines, cancellation, account binding and idempotent retries. `chat.ts` owns the socket/reconnect/acknowledgement lifecycle. `synchronization.ts` owns snapshot serialization; `useDearly.ts` applies it to session/UI state. `usePage.ts` owns cancellable pagination. Feature views consume those boundaries instead of managing transport retries themselves.

### iOS

`APIClient.swift` owns HTTP/WebSocket transport. `APITypes.swift` owns wire payloads and errors; `SessionKeychain.swift` owns secure session persistence; `Localization.swift` owns language lookup. `StateSynchronizer.swift` owns coalesced snapshot reads. `DearlyStore.swift` coordinates authenticated UI state and backend mutations.

`RootView.swift` owns app navigation/lifecycle and `AccountSettingsView.swift` owns account/profile forms. `DesignSystem.swift` retains reusable views and appearance/language controls. Each extracted Swift file is explicitly included in the application target.

## Validation and limits

- Backend: all 103 tests pass after the refactor, including migrations, privacy, staff authorization, idempotency, body limits, concurrent operations, cookies and live sockets. Static checks pass; AST comparison also confirms all 39 extracted top-level helpers/classes preserve their original behavior. The baseline had 102 passing tests.
- Web: all 12 unit tests and the TypeScript/production build pass. The baseline had five unit tests. All eight local WebKit desktop/mobile browser checks pass. Browser coverage includes real account/private-excerpt flows, held-read invalidation, duplicate pagination, system appearance and empty/filled date-field widths in English/Vietnamese at 320, 390 and 1024 pixels.
- CI also builds both Docker images and exercises non-default published/listen ports, runtime backend retargeting, browser sessions, live chat, asset caching and hidden-file rejection. The macOS job builds the iOS app and runs native tests, including the new synchronization regressions.
- The Python runtime dependency audit and npm audit reported no known vulnerabilities for the checked manifests. Their results are point-in-time advisory checks, not proof that every dependency is safe. The existing Starlette/httpx test-client deprecation is outside the runtime path and remains visible.

No database schema or stored user data was changed by this refactor. Existing REST routes, DTO shapes, Swift dates, bearer sessions, browser cookie protections and the default frontend/backend ports remain compatible. The optional account-binding header is additive.

This is a source review and regression pass, not a production penetration test. Physical-device background/foreground behavior, Local Network prompts, accessibility and production TLS/tunnel reachability still need the [manual checklist](MANUAL-TESTS.md). The existing single-worker SQLite/in-memory-event-hub deployment limit, manual age verification and moderation/retention constraints remain as documented in [security](SECURITY.md) and [performance](PERFORMANCE.md).
