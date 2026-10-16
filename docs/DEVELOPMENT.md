# Develop Dearly

[All guides](README.md) · [Local setup](SETUP.md) · [API contract](API.md)

Dearly uses SwiftUI for iOS, React + Vite + TypeScript for web, and a shared FastAPI/SQLite backend. English is the source language, with Vietnamese translations. See [localization](LOCALIZATION.md) when changing interface text or API errors.

## Local web development

Use **Node.js 24**, matching the Docker build and CI. Start the backend on port **8002** using the [Python setup steps](SETUP.md#backend-without-docker). In another terminal, from the repository root:

```bash
cd web
npm ci
npm run dev
```

Open [http://localhost:8003](http://localhost:8003). Vite proxies `/v1`, `/ws`, and `/health` to the backend. Use a consistent hostname throughout login. If you change the backend port, update the targets in `web/vite.config.ts`.

For local development with a built frontend, FastAPI can serve `web/dist` after `npm run build`. Its launcher accepts `--web-dir /absolute/path/to/dist` or `DEARLY_WEB_DIST`. The production API-only Docker image contains no frontend build.

## Checks

From `web`:

```bash
npm test
npm run build
npm audit
npx playwright install chromium
npm run test:e2e
```

The browser fixture starts a backend with the ignored `backend/data/e2e.sqlite3` database. Build the web app first. Use `DEARLY_E2E_BASE_URL` only for an existing disposable instance: these flows create accounts and synthetic entries. Docker CI uses that option to test the actual Nginx proxy. See the [web reference](../web/README.md#checks) for details.

From `backend` on macOS/Linux, after setup:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python benchmark.py
```

On Windows, use `.\.venv\Scripts\python.exe`. The benchmark creates temporary fixture data and chooses a temporary port; the normal server launcher uses the requested port and does not silently select another.

Open `ios/Dearly.xcodeproj` in Xcode, select Dearly, and press **⌘U** for native tests. Use the [manual device checklist](MANUAL-TESTS.md) for layout, accessibility, unreliable networks, and background/foreground behavior.

GitHub Actions runs backend/static/dependency checks, web tests/build/audit and desktop/mobile browser flows, both Docker images with custom ports and live chat checks, and iOS Simulator tests. Check the run for the commit being reviewed. CI does not replace physical-device checks, production HTTPS verification, or App Store/TestFlight distribution. [Validation notes](VALIDATION.md) record earlier checks and their scope.

## Architecture notes

The frontend uses same-origin `/v1/...` and `/ws/chat` routes. Nginx keeps public Host/port, Origin, cookies, and WebSocket upgrades intact when proxying to the configured backend. Native iOS uses bearer sessions in Keychain; web uses HttpOnly cookies. See the [API contract](API.md) for authentication, DTOs, staff permissions, and socket frames.

Web chat sends/receives over WebSocket, with reconnect, deduplication, and an idempotent REST fallback. iOS receives live events, uses idempotent REST sends, and polls for recovery. The event hub is in one backend worker, not a shared message broker. State uses ETags and bounded snapshots; journals, messages, and saved gardens have pagination. [Runtime limits](../backend/README.md#runtime-behavior-and-limits) and [performance notes](PERFORMANCE.md) describe the current pilot constraints.

## Project layout

| Path | Purpose |
|---|---|
| `ios/Dearly/Core/Models.swift` | Codable models and domain rules |
| `ios/Dearly/Core/APIClient.swift` | HTTP and WebSocket transport |
| `ios/Dearly/Core/APITypes.swift`, `SessionKeychain.swift`, `Localization.swift` | Wire DTOs, Keychain session storage and language lookup |
| `ios/Dearly/Core/StateSynchronizer.swift` | Serial, coalesced snapshot reads |
| `ios/Dearly/Core/StaffModels.swift` | Staff roles, reports, account summaries, and audit DTOs |
| `ios/Dearly/Core/DearlyStore.swift` | Backend authentication, synchronization, mutations, and UI state |
| `ios/Dearly/UI/` | Login/signup, journal, community, companion, garden, settings, and staff screens |
| `ios/Dearly/Assets.xcassets/` | Appearance-aware light/dark colors and app icon |
| `ios/Dearly/Localizable.xcstrings` | English source keys and Vietnamese interface translations |
| `ios/Dearly.xcodeproj` | Native Xcode project; relative source paths remain inside ios/ |
| `web/src/` | Responsive React app, English source copy, Vietnamese translations, themes, and same-origin API/chat client |
| `web/e2e/` | Desktop/mobile browser flow tests |
| `web/Dockerfile`, `web/docker/` | Independent frontend image, runtime backend address prompt, Nginx REST/WebSocket proxy |
| `backend/Dockerfile` | API-only image with configurable listen port |
| `configure-docker.py`, `.env.example`, `compose.yaml` | Interactive setup and independent service/port configuration |
| `backend/localization.py`, `backend/translations.vi.json` | English API error templates and Vietnamese responses |
| `backend/server.py`, `backend/dearly/` | Compatible factory entrypoint; modules for database, validation, policies, serialization, services, actions and feature routes |
| `backend/run.py` | Server launcher, role grants, age verification, reports, suspension/restoration, and backups |
| `backend/tests/` | API, privacy, concurrency, and persistence tests |
| `ios/DearlyTests/` | Native model, backend contract, signed-out state, and localization tests |
| `docs/` | Setup, usage, hosting, staff and development guides; API reference and validation notes |

Local databases, virtual environments, credentials, Xcode user settings, and build output are excluded by `.gitignore`.

See the [source audit and module guide](SOURCE-AUDIT.md) for ownership boundaries, fixed concurrency issues and regression coverage.

## Product scope

This is a small-server pilot. Age review and moderation require an operator; automatic identity verification, message filtering, and an appeals dashboard are not implemented. See the [roadmap](ROADMAP.md) for remaining work and [security behavior](SECURITY.md) for privacy and authorization boundaries.
