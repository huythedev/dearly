# Dearly 🌱

A quiet place to write, find someone willing to listen, and grow a little garden together.

**SwiftUI · iOS 17+ · React · Vite · TypeScript · FastAPI · SQLite**

## Run separate frontend and backend containers

The monorepo has `ios/`, `web/`, and the shared `backend/`. Web and iOS use the same accounts and database. Docker now builds **two independent images**: `dearly-web:latest` (React + Nginx) and `dearly-api:latest` (FastAPI + SQLite).

From the repository root, optionally run the configuration wizard to enter the frontend port, backend port, and backend IP/hostname:port:

```bash
python3 configure-docker.py
# Windows: py -3 configure-docker.py
docker compose up -d --build
```

Or copy `.env.example` to `.env` and edit the settings directly. Defaults are **web http://127.0.0.1:8080** and **API http://127.0.0.1:8000**. Both published ports and both internal listen ports can be changed independently. For example:

```dotenv
DEARLY_FRONTEND_PORT=9080
DEARLY_BACKEND_PORT=9100
DEARLY_BACKEND_ADDRESS=backend:8000
```

`backend:8000` is the Compose service's **internal** address, even when its published host port is 9100. For a backend on another machine, enter its reachable address instead, such as `192.168.1.20:9100`; publish that backend on its LAN interface. For a backend running on the Docker host, use `host.docker.internal:9100`. The frontend container can also prompt for this address when launched interactively without `DEARLY_BACKEND_ADDRESS`.

Each service can run alone:

```bash
docker compose up -d --build backend
docker compose up -d --build frontend
```

The frontend serves React and forwards `/v1/*`, `/ws/*`, `/health`, and `/docs` to its configured backend. The browser keeps relative URLs and same-origin cookies; changing the backend address needs only a frontend restart/recreation, not a frontend rebuild. No Caddy or browser CORS configuration is required.

For **dearly.huythedev.com**, point the Cloudflare Tunnel to the **frontend port** (8080 by default), which forwards API/chat internally. An older tunnel pointing at backend port 8000 will reach the API only after this split. The existing `dearly-data` SQLite volume is retained. This repository change does not deploy or edit the running tunnel.

See [web Docker configuration](web/README.md) for independent hosts, interactive startup, port mappings, and tests. For development without Docker, Vite can proxy to a local backend; FastAPI's optional built-web hosting remains available for local development.

## Run the iOS app

1. Open `ios/Dearly.xcodeproj` in Xcode 26 or newer (deployment target: iOS 17+).
2. Select the **Dearly** scheme and an iPhone Simulator, then press **⌘R**. For a physical device, configure your signing team first.
3. Log in or create an account. The default backend address is **`https://dearly.huythedev.com`**. A previously saved server address takes precedence.
4. To use a different backend, expand **Server connection / Kết nối server** on the login screen and enter its base URL.

The app requires a backend account. It starts at login, restores a saved session when possible, and returns to login after logout or session expiry. There is no offline demo fallback. Journal entries, messages, and account changes are saved through the backend; session tokens are stored in Keychain.

The interface uses **English as its source language and default**, with **Vietnamese translations**. Use the language menu on the login screen or open your avatar → **Language / Ngôn ngữ** in settings. Your language choice is saved between launches, including an existing Vietnamese choice; user-written content is not translated. See the [localization guide](docs/LOCALIZATION.md) for source strings, API errors, and compatibility.

**Dark mode:** use the appearance icon on the login screen or your avatar → **Appearance / Giao diện**. Choose **System** (default), **Light**, or **Dark**. The choice is saved between launches and applies to login, journals, community, chat, gardens, settings, and staff screens. The garden uses a moon and darker landscape in dark mode.

## Run a local backend

For API-only/iOS use, no separate database installation, Docker, Redis, or Node.js is required. Run these commands from the repository root.

### macOS / Linux

```bash
cd backend
python3 setup.py
.venv/bin/python run.py serve
```

### Windows PowerShell

```powershell
cd backend
py -3 setup.py
.\.venv\Scripts\python.exe run.py serve
```

Setup creates `backend/.venv` and installs the pinned dependencies. The server defaults to **`127.0.0.1:8000`**, with health status at `http://127.0.0.1:8000/health` and interactive API documentation at `http://127.0.0.1:8000/docs`.

**The launcher does not automatically select another port.** If port 8000 is occupied, choose one explicitly:

```bash
.venv/bin/python run.py serve --port 8001
```

For local development, build the iOS app in **Debug** and change its server address on the login screen:

| Client | Server address | Backend binding |
|---|---|---|
| Simulator on the same Mac | `http://localhost:8000` | Default localhost binding |
| Physical iPhone on the same Wi-Fi | `http://<computer-LAN-IP>:8000` | `serve --host 0.0.0.0 --port 8000` |

If you change the backend port, update the app URL as well. `localhost` on an iPhone refers to the phone itself. Release builds require HTTPS with a trusted certificate.

Alternatively, with Docker and Docker Compose installed, run from the repository root:

```bash
docker compose up -d --build backend
```

This builds the API-only `dearly-api:latest` image and runs it on `127.0.0.1:8000` with persistent SQLite storage. Set `DEARLY_BACKEND_PORT` in `.env` to change its published port. See the [Docker instructions](backend/README.md#docker) for logs, administration, backups, and stopping the service.

See the [backend README](backend/README.md) for database paths, LAN troubleshooting, HTTPS hosting, administration, Docker, and tests.

## Features

- Private journals with editing, deletion, sharing previews, full-entry or excerpt sharing, and anonymous community posts.
- Anonymous stories support comments, reporting, and hiding a single story. Invitations use identified profiles; named-account blocks do not filter anonymous stories, which would reveal their authors. Avoid including identifying details in anonymous writing.
- Community listening and responses based on the writer’s chosen support preference.
- Companion suggestions based on stated interests and verified age eligibility. Both people must agree before chat opens.
- Chat, server-side reports, blocking, and leaving connections.
- Daily check-ins by both companions, garden pauses, streaks, total days, and saved rewards. Browse every saved garden with archive pagination.
- Gardens drawn in SwiftUI on iOS and SVG on web, without downloaded artwork.
- Browser chat uses authenticated WebSockets with reconnect, message deduplication, and idempotent REST fallback. iOS receives live events over WebSocket and keeps idempotent REST sends; native REST chat immediately notifies connected iOS/web clients.
- ETag synchronization, retry backoff, and idempotent mutations. Web checks state every 15 seconds while visible and on socket invalidation; iOS uses 15-second reconciliation while its socket is connected and 3-second polling as a fallback. Journals, messages, and saved gardens support pagination.
- In-app report moderation and account administration with server-enforced roles and an audit log.

## Roles and administration

New accounts always start as **User**. On iOS, staff open their avatar → **Dearly management / Quản lý Dearly**. On web, use **Management**, or **Settings → Management** on mobile. Access is checked by the backend on every request; changing the client UI or sending a forged role does not grant permissions.

| Function | User | Moderator | Admin |
|---|:---:|:---:|:---:|
| Personal journals, community, companions, garden, block/report | ✓ | ✓ | ✓ |
| Read reports and their reported public excerpts | — | ✓ | ✓ |
| Mark reports open, reviewed, or dismissed with a note | — | ✓ | ✓ |
| Restrict/restore sharing of a reported community post | — | ✓ | ✓ |
| Search accounts; review birth dates and verify age | — | — | ✓ |
| Suspend/restore users and moderators | — | — | ✓ |
| Assign/remove moderator access | — | — | ✓ |
| Read the administration audit log | — | — | ✓ |
| Grant/revoke admin or modify an admin account | Server CLI only | Server CLI only | Server CLI only |

Create the account through the app first, then grant admin on the **backend host**. Run from `backend` using the same database as the running server:

```bash
# macOS / Linux
.venv/bin/python run.py set-role --username YOUR_USERNAME --role admin --reason "Initial administrator"
```

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe run.py set-role --username YOUR_USERNAME --role admin --reason "Initial administrator"
```

```bash
# Docker Compose, from the repository root
docker compose exec backend python run.py set-role --username YOUR_USERNAME --role admin --reason "Initial administrator"
```

For a custom database, put `--db /path/to/dearly.sqlite3` **before** `set-role`, or use the same `DEARLY_DB` environment variable as the server. The CLI can also set `--role moderator` or `--role user`. There is no default admin password or public admin-registration endpoint. Changes appear on the next sync; use **Sync now** in settings if needed. The last active admin cannot be demoted or suspended.

Staff access does not allow browsing other people's private journal bodies or chat transcripts. A report about a public post retains only its published excerpt as evidence, including after the author withdraws/deletes that post; authorized staff can identify the reported account. Hiding a post preserves its author's private journal, removes community comments, and restricts further sharing until staff allow it again. Private edits remain available. Account suspension revokes sessions and ends connections while keeping garden rewards; restoring an account requires a fresh login. Staff mutations and CLI administration record the actor and reason in the audit log. See the [backend guide](backend/README.md#roles-and-the-in-app-staff-console) for migration and operational details.

To try the companion flow, create two accounts on separate devices or simulators. An operator must verify each account’s birth date using the [administration CLI](backend/README.md#age-verification-and-administration) before matching becomes available.

## Project layout

| Path | Purpose |
|---|---|
| `ios/Dearly/Core/Models.swift` | Codable models, domain rules, and localization helpers |
| `ios/Dearly/Core/APIClient.swift` | HTTP requests, session storage, and API DTOs |
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
| `backend/server.py` | API, authentication, authorization, and SQLite transactions |
| `backend/run.py` | Server launcher, role grants, age verification, reports, suspension/restoration, and backups |
| `backend/tests/` | API, privacy, concurrency, and persistence tests |
| `ios/DearlyTests/` | Native model, backend contract, signed-out state, and localization tests |
| `docs/` | API reference, roadmap, manual checks, and historical validation notes |

Local databases, virtual environments, credentials, Xcode user settings, and build output are excluded by `.gitignore`.

## Validation and limitations

This environment has no Xcode or iOS Simulator. A GitHub Actions job builds and runs native tests on an available iPhone Simulator; its result is separate from the local backend checks. Device rendering still needs the [manual checklist](docs/MANUAL-TESTS.md).

The backend regression suite covers the security fixes, role boundaries, database upgrades, persistent moderation, upload timeouts, and complete garden archives. See [validation notes](docs/VALIDATION.md) and [security behavior](docs/SECURITY.md). GitHub Actions runs backend/security tests, frontend contract tests/build/audit, desktop/mobile browser flows, separate Docker image, custom-port, remote-upstream, cookie, and WebSocket smoke tests, and native iOS tests from `ios/Dearly.xcodeproj`. Windows/macOS backend execution, Docker, public HTTPS deployment, and App Store/TestFlight distribution have not been verified locally.

This is a small-server pilot. Age verification and moderation require an operator; there is no automatic identity verification, message moderation, or appeals dashboard. See the [roadmap](docs/ROADMAP.md) for remaining work. Dearly is a space for companionship, not a therapy service.

Licensed under the [MIT License](LICENSE). Copyright (c) 2026 Huy Nguyen.
