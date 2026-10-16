# Deployment ports and Oracle tunnel — 2026-10-16

- Fresh configuration defaults to frontend 8003, backend 8002, and Compose upstream `backend:8002`. Docker images, Compose mappings, the setup wizard, native launcher, Vite proxy, and deployment instructions agree. Existing operator overrides are retained.
- Local checks passed: 102 backend/configuration tests, 5 web unit tests, production build, Python static checks, shell/Node syntax, and native English/Vietnamese server-help consistency. A real local startup confirmed API health on 8002 and React plus proxied health on 8003.
- iOS login defaults and placeholder share `APIClient.defaultServerAddress` (`https://dearly.huythedev.com`); the native socket test validates that origin and its `wss://` endpoint. Saved custom server addresses keep precedence. Native Simulator and Docker integration results are recorded in the PR's CI checks.
- Cloudflare `Oracle_VPS` Dearly ingress was updated to `http://127.0.0.1:8003` and verified by reading configuration version 11 back. Dearly DNS already targets this tunnel. All other tunnel configuration was preserved. Public application reachability was not required because the containers have not been deployed.

The notes below describe earlier revisions.

# Independent Docker services — 2026-10-16

- Backend + configuration regression suite: 102 tests passed locally, including 15 startup/setup tests for independent ports, preserving existing environment settings, interactive backend input, cancellation, malformed addresses, and template injection rejection.
- Shell and Node smoke scripts pass syntax checks; Python static checks pass. The local environment has no Docker daemon.
- CI builds the API-only and frontend-only images and tests non-default host/internal ports, real WebSocket send/delivery, shared REST idempotency, cookie/CSRF handling, and desktop/mobile browser flows. It then recreates the frontend without a rebuild to reach the same backend through a Docker host mapping and repeats those checks.

The notes below describe earlier revisions.

# Web monorepo and realtime validation — 2026-10-16

- Local backend: 87 tests passed, including same-origin browser cookies, SPA/API route boundaries, member-only socket delivery, REST/socket idempotency, expiry/suspension, frame size, and per-account connection limits.
- Web: TypeScript/Vite production build passed; 5 contract/retry tests passed. npm audit and the pinned backend dependency audit reported no known vulnerabilities. Python static checks passed.
- iOS now receives live messages/state invalidation using URLSessionWebSocketTask, cancels on background/logout, reconnects with backoff, and keeps REST sends/polling for compatibility. Added native URL/DTO/deduplication/membership tests.
- Local environment has no Xcode, Docker, or browser-control surface. CI is configured for an iPhone Simulator, desktop/mobile Playwright flows, and the combined Docker web/API image. Those executions must be reported separately from the local checks.

The notes below describe earlier revisions.

# Validation — English source and Vietnamese translations, 2026-10-16

- **77 backend tests passed** on Linux/Python 3.12, including 21 localization cases for language negotiation, translated static/dynamic errors, upload rejection, credential-safe validation, stable support identifiers, legacy inputs, database migration, and English defaults after an older schema upgrade.
- Catalog checks verify English source configuration, Vietnamese translations, matching positional/named placeholders, and coverage of literal interface keys and backend error templates.
- Native tests now cover the English default/fallback, saved Vietnamese preference, translated formatting with literal user content, and canonical/legacy support decoding. GitHub Actions builds and runs the iOS tests on a simulator; check the result for the specific commit.
- User-written text and the existing Vietnamese language preference are preserved. SQLite v4 changes only known support enum values. Upgrade the app and backend together, as described in [localization](LOCALIZATION.md).
- Local Linux cannot run Xcode. Device layout/VoiceOver, Docker, Windows/macOS backend execution, and production deployment remain outside this local validation.

## Historical validation — security fixes, 2026-10-16

- **56 backend tests passed** on Linux/Python 3.12, including 23 added regression cases for the audit findings and adjacent bugs. A real loopback HTTP test verifies upload admission, timeout responses, and continued health availability. Private/hidden entries retain their author's anonymous sharing preference.
- A separate real-HTTP two-account smoke test passed: login/registration, invitation acceptance, messaging, check-ins, and conditional state synchronization with 300 journal fixtures.
- **517 payload-type variations** across mutation handlers completed without unexpected exceptions; each trial rolled back its database changes. This was an exploratory input-validation check, not a production test.
- Ruff `F,E9`, Python compilation, and whitespace checks passed. The dependency advisory scan reported no known vulnerabilities across the 14 pinned runtime packages, including the formerly unpinned OpenTelemetry dependency.
- Bandit's SQL-construction warnings were reviewed: interpolated fragments are fixed clauses or generated parameter placeholders, with user values bound separately. Development subprocess/assert/fixture-password alerts do not establish a runtime exploit.
- Native XCTest coverage was added for signed-out model access, Gregorian UTC dates, anonymous invitation guards, independent anonymous visibility, and archived garden DTOs. The `ios` GitHub Actions job performs the simulator build and XCTest run; check its result for the specific PR commit. Local Linux checks do not replace native validation.
- Database upgrade coverage includes v1→v3 preservation and v2→v3 reconstruction of earlier moderation restrictions, cancellation of unsafe anonymous invitations, repeated startup, and foreign-key integrity.
- Remaining manual scope: iPhone layout/VoiceOver, Windows/macOS backend operation, Docker, the production proxy/TLS boundary, and App Store/TestFlight distribution.

## Historical validation — roles and appearance, 2026-10-16

- **33 backend pytest tests passed** on Linux/Python 3.12 with the repository's pinned runtime dependencies. This includes the original 21 cases plus authorization, attempted role escalation, moderator review/hiding, live demotion and replay rejection, admin suspension/restoration, CLI bootstrap/last-admin protection, pagination, and v1→v2 migration preserving existing data.
- The test runner reports one upstream Starlette warning about its httpx TestClient adapter; there were no test failures.
- Swift grammar, Xcode source/resource references, light/dark asset JSON, and Info.plist checks passed. `staff-responses.json` was exported from actual API responses; an added native XCTest decodes the state role, staff reports/accounts/audit DTOs, including a CLI reviewer ID. The older state fixture verifies absence of staff fields stays compatible.
- **Not verified for this revision:** native Swift compilation/type checking, Xcode builds/XCTest, Simulator/device rendering, Windows/macOS execution, Docker, or deployment. This environment has no Apple SDK or Simulator. Run the expanded manual checklist and native tests on a Mac.

## Historical validation — 2026-10-14

### Completed at that revision

- 21 API pytest cases passed on Linux/Python 3.12, covering HTTP contracts, privacy/anonymous aliases, authentication/logout/expiry, age/birth-date gates, consent, concurrent writes, duplicate check-ins, streaks/reward retention, pause/leave/block/report, idempotent retries, pagination, and database restart.
- A real localhost Uvicorn server passed registration of two accounts, fixture age verification, invitation send/accept, messages from account A read by B, and both check-ins.
- A sequential HTTP benchmark used 300 journal fixtures; results and limitations are in PERFORMANCE.md.
- `ios/DearlyTests/Fixtures/server-state.json` was exported from actual API responses without tokens or other users' private journal content. A native XCTest decodes the fixture to detect wire-contract drift in Xcode.
- Swift grammar, Xcode structure/source references, scheme XML, asset catalogs, and Debug/Release Info.plist checks completed.
- CLI help/database initialization and source packaging checks completed.

### Not completed at that revision

- Apple Swift compilation/type checking/linking, xcodebuild, the 17 native XCTest cases, code signing, Simulator/device operation, and layout/VoiceOver checks.
- Actual Windows/macOS execution, Docker builds, or GitHub Actions runs. A Windows/macOS/Linux × Python 3.11/3.12/3.13 matrix had been prepared.
- Large concurrent load tests, a public TLS server, or App Store/TestFlight release.

That environment had no Swift compiler, Xcode/Apple SDK, or iOS Simulator. Parser checks do not replace an Xcode build. Run ⌘U on a Mac followed by MANUAL-TESTS.md; passing backend tests does not establish that the iOS interface works on a device.
