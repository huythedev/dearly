# Dearly 🌱

A quiet place to write, find someone willing to listen, and grow a little garden together.

**SwiftUI · iOS 17+ · Python 3.11+ · FastAPI · SQLite**

## Run the iOS app

1. Open `Dearly.xcodeproj` in Xcode with an iOS 17 or newer SDK.
2. Select the **Dearly** scheme and an iPhone Simulator, then press **⌘R**. For a physical device, configure your signing team first.
3. Log in or create an account. The default backend address is **`https://api.dearly.huythedev.com`**. A previously saved server address takes precedence.
4. To use a different backend, expand **Server connection / Kết nối server** on the login screen and enter its base URL.

The app requires a backend account. It starts at login, restores a saved session when possible, and returns to login after logout or session expiry. There is no offline demo fallback. Journal entries, messages, and account changes are saved through the backend; session tokens are stored in Keychain.

The interface supports **English and Vietnamese**. Use the language menu on the login screen or open your avatar → **Language / Ngôn ngữ** in settings. Your language choice is saved between launches; user-written content is not translated.

## Run a local backend

No separate database installation, Docker, Redis, or Node.js is required. Run these commands from the repository root.

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

See the [backend README](backend/README.md) for database paths, LAN troubleshooting, HTTPS hosting, administration, Docker, and tests.

## Features

- Private journals with editing, deletion, sharing previews, full-entry or excerpt sharing, and anonymous community posts.
- Community listening and responses based on the writer’s chosen support preference.
- Companion suggestions based on stated interests and verified age eligibility. Both people must agree before chat opens.
- Chat, server-side reports, blocking, and leaving connections.
- Daily check-ins by both companions, garden pauses, streaks, total days, and saved rewards. Leaving a connection or breaking a streak preserves garden rewards.
- Gardens drawn in SwiftUI, without downloaded artwork.
- Foreground synchronization about every 3 seconds, ETag responses, retry backoff, and idempotent mutations. Personal journals and chat support pagination.

To try the companion flow, create two accounts on separate devices or simulators. An operator must verify each account’s birth date using the [administration CLI](backend/README.md#age-verification-and-administration) before matching becomes available.

## Project layout

| Path | Purpose |
|---|---|
| `Dearly/Core/Models.swift` | Codable models, domain rules, and localization helpers |
| `Dearly/Core/APIClient.swift` | HTTP requests, session storage, and API DTOs |
| `Dearly/Core/DearlyStore.swift` | Backend authentication, synchronization, mutations, and UI state |
| `Dearly/UI/` | Login/signup, journal, community, companion, garden, and settings screens |
| `Dearly/Localizable.xcstrings` | English and Vietnamese interface translations |
| `backend/server.py` | API, authentication, authorization, and SQLite transactions |
| `backend/run.py` | Server launcher, age verification, reports, suspension, and backups |
| `backend/tests/` | API, privacy, concurrency, and persistence tests |
| `DearlyTests/` | Native model, backend contract, signed-out state, and localization tests |
| `docs/` | API reference, roadmap, manual checks, and historical validation notes |

Local databases, virtual environments, credentials, Xcode user settings, and build output are excluded by `.gitignore`.

## Validation and limitations

The iOS Simulator Debug build has passed. The simulator stopped responding during the native test run, so native test results and visual verification remain unconfirmed. Run **⌘U** in Xcode and follow the [manual checklist](docs/MANUAL-TESTS.md).

The [historical validation notes](docs/VALIDATION.md) record 21 passing backend tests on Linux and a two-account HTTP flow. Local setup and the backend health endpoint were also checked on macOS. Windows execution, Docker, public HTTPS deployment, and App Store/TestFlight distribution have not been verified in this session. No GitHub Actions workflows are currently included in this checkout.

This is a small-server pilot. Age verification and moderation require an operator; there is no automatic identity verification, message moderation, or appeals dashboard. See the [roadmap](docs/ROADMAP.md) for remaining work. Dearly is a space for companionship, not a therapy service.

Licensed under the [MIT License](LICENSE). Copyright (c) 2026 Huy Nguyen.
