# Dearly backend 0.5

For guided setup and everyday use, start with the [setup guide](../docs/SETUP.md) and [user guide](../docs/USAGE.md). This page contains the component reference.

A Python 3.11+ / FastAPI / SQLite backend shared by the Dearly iOS and web apps. It runs as a single server on macOS, Linux, or Windows. No separate database server, Redis, Node.js runtime, or Docker is required. Building the optional web frontend requires Node.js 24 or the Docker multi-stage build.

Implementation is organized in `dearly/`; `server.py` preserves the app factory and CLI imports. See the [module guide](../docs/SOURCE-AUDIT.md#backend) for responsibilities.

## Setup and run

Open a terminal in the repository’s `backend` directory.

### macOS / Linux

```bash
python3 setup.py
.venv/bin/python run.py serve
```

### Windows PowerShell

```powershell
py -3 setup.py
.\.venv\Scripts\python.exe run.py serve
```

`setup.py` creates a local `.venv` and installs the pinned packages in `requirements.txt`. You do not need to activate the environment. On Linux, install your distribution’s `python3-venv` package if environment creation reports that it is missing.

`run.py serve` listens on **`127.0.0.1:8002`** by default. Stop it with **Ctrl+C**.

- Health: `http://127.0.0.1:8002/health`
- Interactive API docs: `http://127.0.0.1:8002/docs`

### Port conflicts and LAN access

The launcher uses the requested port and **does not automatically switch ports**. If port 8002 is already occupied, stop the other service or choose a different port:

```bash
.venv/bin/python run.py serve --port 8001
```

To allow a physical iPhone or another computer on your LAN to connect:

```bash
.venv/bin/python run.py serve --host 0.0.0.0 --port 8002
```

On Windows, use `.\.venv\Scripts\python.exe` in place of `.venv/bin/python` in these and subsequent commands. When changing the port, also update the app’s server URL and any reverse proxy configuration.

### Database location

SQLite is created automatically at `data/dearly.sqlite3`, relative to the working directory. Running from `backend` therefore creates `backend/data/dearly.sqlite3`.

For a service, use an absolute path through `--db` or the `DEARLY_DB` environment variable. Global `--db` must appear **before** the subcommand:

```bash
.venv/bin/python run.py --db /absolute/path/dearly.sqlite3 serve --port 8002
```

Administration commands must use the same database path as the running server. Virtual environments, local databases, and backups are excluded by the repository’s `.gitignore`.

## Connect the iOS app

The app’s default server is **`https://dearly.huythedev.com`**. This is a client default; running the local backend does not configure DNS, TLS, or deployment for that domain. Previously saved server addresses and sessions keep their existing server URL.

1. Open `ios/Dearly.xcodeproj` from the repository root, select the **Dearly** scheme, and run a **Debug** build on a simulator or iPhone.
2. On the login screen, expand **Server connection / Kết nối server** to choose your backend.
3. For a simulator on the same Mac, enter `http://localhost:8002`.
4. For a physical iPhone, use the computer’s LAN IP, such as `http://192.168.1.10:8002`. Bind the backend to `0.0.0.0`, connect both devices to the same Wi-Fi, and allow Local Network access if prompted. Do not use `localhost` to reach your computer from an iPhone.
5. Register or log in. Usernames use 3–64 characters from `a-z A-Z 0-9 _ . -`; passwords use 10–128 characters; nicknames allow up to 40 characters.
6. To test matching and chat, create two accounts on separate devices or simulators and verify their birth dates with the administration CLI below.

The app requires a backend session and has no offline demo fallback. New accounts can write journals immediately; matching requires operator-verified age. While the iOS app is open, WebSocket events deliver chat and invalidate state immediately. It reconciles every 15 seconds when connected and falls back to 3-second REST sync when disconnected. English is the default and source language; choose Vietnamese from the login screen’s language menu or account settings. API errors default to English and support `Accept-Language: vi`. Stored support preferences use `listen`, `relate`, or `brainstorm`, independently of display language.

Debug builds allow HTTP to localhost, private IPv4 addresses, and `.local` hosts. Release builds require HTTPS. The API client rejects redirects and uses normal certificate validation; a self-signed certificate must be trusted by iOS to work.

For LAN connection problems, check the URL and port, backend binding, Local Network permission, host firewall, and Wi-Fi client isolation. On Windows, allow inbound TCP on the chosen port for the **Private** network profile when needed. Use HTTP development connections only with test data on a trusted network.

## Age verification and administration

Run these commands from `backend`, using the same database as the server. The sample birth dates are for test accounts you control; real verification must use the person’s reviewed birth date.

```bash
.venv/bin/python run.py verify-age --username alice --birth-date 2009-01-01
.venv/bin/python run.py verify-age --username bravo --birth-date 2009-04-01
.venv/bin/python run.py reports
.venv/bin/python run.py resolve-report --id REPORT_UUID
.venv/bin/python run.py suspend --username USERNAME
.venv/bin/python run.py backup --output backups/dearly-backup.sqlite3
```

`verify-age` records that an operator reviewed the birth date outside the app. It does not automatically verify identity documents. Do not store identity document images in this app or database. Correcting a birth date ends existing connections so eligibility can be checked again; verifying the same date again does not end them.

Registration supports ages 16–100. Age is calculated using the UTC date and checked again when sending or accepting invitations, sending messages, and checking in. Under-18 accounts can connect only with other under-18 accounts at most one year apart. Adults form a separate group. Regular users cannot set `ageVerified` or change birth dates. A moderator or admin using the staff console/API, or an operator using the CLI, can record a reviewed birth date for an eligible account.

Reports are stored on the server. `reports` lists up to 100 open reports for an operator with host access. `suspend` revokes sessions and ends connections while retaining garden rewards. `restore --username USERNAME` re-enables login without restoring old sessions or connections. The iOS staff console supports manual report review; automatic message filtering and an appeals workflow are not implemented.

### Roles and the in-app staff console

| Role | Permissions |
|---|---|
| `user` | Standard Dearly features; no staff endpoints |
| `moderator` | `reports.read`, `reports.review`, `reports.hide`, `users.read`, `users.verify_age` |
| `admin` | All moderator permissions plus `users.suspend`, `roles.manage`, `audit.read` |

Staff open **avatar → Dearly management** in the iOS app. Reports can be reopened, marked reviewed, dismissed, or used to withdraw a reported public post. Moderators and admins can search accounts by username/nickname prefix and confirm externally reviewed birth dates. Admins can also suspend/restore non-admin accounts, assign/remove moderators, and inspect the audit log. See the [age review steps](../docs/ADMINISTRATION.md#age-verification) for iOS and web. Every mutation requires a reason. Each list uses bounded pagination (30 records by default, at most 50); the app retains only the displayed page.

Create the account normally, then run on the server host from `backend`:

```bash
# macOS / Linux
.venv/bin/python run.py set-role --username YOUR_USERNAME --role admin --reason "Initial administrator"
.venv/bin/python run.py set-role --username REVIEWER --role moderator --reason "Report review duty"
.venv/bin/python run.py set-role --username REVIEWER --role user --reason "Review duty ended"
```

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe run.py set-role --username YOUR_USERNAME --role admin --reason "Initial administrator"
```

```bash
# Docker Compose, from repository root
docker compose exec backend python run.py set-role --username YOUR_USERNAME --role admin --reason "Initial administrator"
```

`set-role` accepts `user`, `moderator`, or `admin` and requires `--reason`. It acts on an existing username (case-insensitive). It does not create a login or a password. Use `--db PATH` **before the subcommand**, or the same `DEARLY_DB` used by the running server; the default is `data/dearly.sqlite3` relative to the working directory. Docker already sets `DEARLY_DB=/data/dearly.sqlite3`.

Only the server CLI can grant/revoke admin or change an admin account. The API rejects self-management and admin targets. Demoting or suspending the last non-suspended admin is rejected; grant a replacement admin first. All accounts, including existing accounts after migration, default to `user`. Public signup/profile updates cannot grant roles. Roles are read from the database for every request, including retries, so demotion takes effect immediately without waiting for token expiry. The iOS staff entry updates on the next state sync.

Reports contain the submitted reason and, for a reported community post, a snapshot of its **published excerpt**. Staff can identify accounts involved in a report, including anonymous posts. Private journal bodies, unshared text, and chat transcripts are not exposed by staff endpoints. The excerpt remains in the report after the original post is withdrawn or deleted. Hiding a reported post makes it private, deletes its community comments/listening reactions, and restricts further sharing of that entry. The author can keep editing privately. Staff can choose **Allow the author to share again** after review; this is audited and leaves the entry private until its author chooses to share it.

Staff and CLI mutations append an audit event in the same transaction: actor user ID (or `server-cli`), action, target, reason, and timestamp. No password, token, or birth date is placed in audit details. Staff HTTP responses use `Cache-Control: no-store`. The audit log is admin-readable through the API, has no client edit/delete endpoint, and is not tamper-proof against an operator with direct database access. Reports/audit events have no automatic retention cleanup yet; include their retention in the pilot's operational policy.

### Upgrading an existing database

Use the previous checkout's backup command before upgrading. Stop the old backend, update/install the pinned requirements, then restart. Startup migrates SQLite v1/v2/v3 to `user_version=4` in a transaction. It preserves accounts, sessions, journal bodies, reports, connections, and rewards; reconstructs durable sharing restrictions from earlier staff hide audit events; cancels old pending anonymous invitations; and converts predefined Vietnamese support values to stable English identifiers. Free-form profile text and journal content are preserved. New accounts receive English defaults even on databases with older column defaults.

Update the iOS app and backend together: the new app can read older Vietnamese support values, and the backend accepts those legacy inputs, but older apps cannot decode the new identifiers in responses. Anonymous stories offer **Hide this story**, with invitations/account blocking available through identified profiles. Repeated startup/CLI access is safe. The default single-worker SQLite setup is unchanged. Do not run the old backend against an upgraded database; rollback requires the pre-upgrade backup and matching code. See the [localization guide](../docs/LOCALIZATION.md).

### Backups

Use the CLI’s SQLite backup operation rather than copying only the `.sqlite3` file while WAL is active. Choose a new output filename for each backup; the command refuses to overwrite an existing file. Backups contain user data and should be accessible only to operators.

Keep SQLite on a local disk, not SMB/NFS. Do not run multiple replicas writing to the same file.

## HTTPS hosting

Docker deployment uses a separate frontend container. Point the public **dearly.huythedev.com** Cloudflare Tunnel at that frontend's published port (8003 by default). It serves React and proxies API, WebSocket, and documentation routes to this backend, preserving the browser's Host **including its port** and Origin. Native iOS can use that same public origin or connect to a separately secured backend endpoint.

The frontend accepts an HTTP backend IP/hostname:port or an HTTPS origin with a trusted certificate. Configure `DEARLY_BACKEND_ADDRESS` on the frontend, not in browser JavaScript. It must be reachable from that container; `localhost` refers to the frontend itself. No browser CORS allowlist is needed.

Only trust actual frontend/reverse-proxy addresses when enabling forwarded client IPs: use `DEARLY_PROXY_IPS` or `serve --proxy-ips` with explicit addresses. The frontend overwrites X-Forwarded-For with its observed client IP. Without trusted proxy configuration, backend limits group traffic by the frontend's IP. Behind Cloudflare, account for the tunnel/proxy chain when choosing the trusted boundary. Forwarded headers are ignored by default.

For non-Docker local development, optional FastAPI hosting of `web/dist` is still supported. Build in `web/`, then start normally; override discovery with `serve --web-dir /absolute/path/to/dist` or `DEARLY_WEB_DIST`. Explicit missing builds fail startup. The API-only Docker image contains no web assets.

## Docker

Install Docker Engine with the Compose plugin, or Docker Desktop. Frontend and backend build/run independently; SQLite stays in the existing `dearly-data` volume.

### Compose (repository root)

```bash
python3 configure-docker.py  # Windows: py -3 configure-docker.py
# Or copy .env.example to .env and edit it.
docker compose up -d --build backend
docker compose ps
docker compose logs -f backend
```

Set `DEARLY_BACKEND_PORT=9100` to publish the API on a different host port. `DEARLY_BACKEND_BIND` defaults to 127.0.0.1; set 0.0.0.0 or the host's LAN interface to allow a frontend on another machine. `DEARLY_BACKEND_LISTEN_PORT` sets the container's internal port (default 8002); health checks and Compose port mappings follow it. When changing that internal port, update the frontend's backend address too. Legacy `DEARLY_PORT` / `DEARLY_BIND` in a root `.env` still provide host-port/bind defaults, but the new names are preferred.

Start both services with `docker compose up -d --build`, or start only the frontend with `docker compose up -d --build frontend` and a reachable `DEARLY_BACKEND_ADDRESS`. The frontend and backend have no forced startup dependency and can be deployed to different machines.

```bash
docker compose exec backend python run.py reports
docker compose exec backend python run.py verify-age --username alice --birth-date 2009-01-01
docker compose exec backend python run.py backup --output /data/dearly-backup.sqlite3
docker compose cp backend:/data/dearly-backup.sqlite3 ./dearly-backup.sqlite3
docker compose down
```

`docker compose down` preserves the named volume. Adding `--volumes` deletes it. Keep the same Compose project/directory when upgrading so the existing volume is reused. Stop the old combined backend before assigning its old published port to the new frontend.

### Without Compose (repository root)

```bash
docker build -t dearly-api:latest backend
docker run -d --name dearly-api --restart unless-stopped --init -p 127.0.0.1:9100:8002 -v dearly-data:/data dearly-api:latest
```

For a custom internal port as well:

```bash
docker run -d --name dearly-api-custom --init -e DEARLY_PORT=8200 -p 127.0.0.1:9100:8200 -v dearly-data:/data dearly-api:latest
```

Both run with a non-root user. The image has no Node/React/Nginx dependency. `backend/.dockerignore` allows only API runtime inputs and excludes local databases, credentials, environments, tests, and backups. Administration commands remain `docker exec dearly-api python run.py ...`. When using host-native Python, `DEARLY_PORT` sets the launcher's default port and explicit `--port` takes precedence.

## Tests

From `backend` on macOS/Linux:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python benchmark.py
```

On Windows, use `.\.venv\Scripts\python.exe`. The benchmark starts a real HTTP server on a temporary localhost port and removes its temporary fixture data afterward. This temporary-port behavior belongs to the benchmark; the normal server launcher does not choose a free port automatically.

The backend suite covers staff authorization, migration, the audit regressions, and real HTTP upload admission/timeouts. See the [validation notes](../docs/VALIDATION.md). GitHub Actions runs backend/static/dependency checks and native iOS tests. Windows/macOS backend execution and Docker are not available locally; CI exercises the two Docker images, independent custom ports, proxy cookie auth, and live chat through both Compose DNS and a host-mapped backend.

## Runtime behavior and limits

- Uvicorn uses standard `asyncio` and `h11`, with one worker and a concurrency limit of 64. Synchronous endpoints use up to 16 threads, and password hashing allows at most two simultaneous operations.
- SQLite uses WAL, indexes for common queries, and `BEGIN IMMEDIATE` transactions for invitation and check-in consistency. There is one writer at a time, with a 2 MiB cache per connection.
- Request bodies are limited to 128 KiB and expire after 5 seconds without a chunk or 15 seconds total. At most 32 bodies can be read concurrently, at most 8 per client IP; excess uploads receive 429 before parsing/authentication, leaving capacity for body-free reads/health. Timeouts return 408 and close the connection. The launcher supports `--body-idle-timeout SECONDS` and `--body-total-timeout SECONDS`. Keep proxy/header deadlines and origin access restrictions as well; these application controls start after HTTP headers are received.
- Journals are limited to 20,000 characters; messages to 4,000; responses to 2,000. The rate limiter holds at most 4,096 buckets in memory.
- State snapshots return bounded windows: up to 60 personal journals, 60 community posts, 60 companion journals, 20 recent gardens plus the active connection if needed, 100 invitations, 200 responses, and 100 recent messages.
- Personal journal pagination uses 40 entries per page in the app, with an API maximum of 60. Saved gardens use 20 per page (API maximum 50) with member profiles included. Chat supports up to 100 messages per API page; the app retains at most 500 messages in memory. Community and companion journal screens show the latest window without older-history navigation.
- iOS receives live socket messages/invalidation with foreground-aware reconnect and idempotent REST sends, using 15-second reconciliation or 3-second polling while disconnected. Web uses `/ws/chat` for sending/receiving chat, immediate state invalidation, exponential reconnect, and an idempotent REST send fallback. Visible web tabs also poll state every 15 seconds for recovery and CLI changes. There is no background push delivery after a client closes. The event hub is single-worker, bounded to 32 sockets globally / 4 per account, with 32 queued notifications each; slow clients resync instead of accumulating an unbounded message backlog. Session/suspension is rechecked on each frame/event and every 15 seconds while idle. Uvicorn/wsproto limits assembled frames to 16 KiB; authentication must arrive within 5 seconds.
- Mutations use request UUIDs. Results are stored in the same transaction so retrying a request does not duplicate a message. Retry keys are retained for 7 days; daily check-ins have a separate UTC uniqueness constraint.
- Passwords use salted PBKDF2-SHA256 with 600,000 iterations. Random bearer tokens are stored only as hashes on the server, expire after 30 days, and are kept in Keychain on iOS and in HttpOnly session cookies on web. Browser tokens never appear in JavaScript storage, URLs, or web authentication response bodies. Cookie-authenticated writes require the same-origin web header; cross-origin WebSocket handshakes are denied. App session state stays in memory rather than being written to a local journal/chat cache.

This design targets a small, controlled pilot. Larger write volumes or multiple replicas require a server database and more targeted cache invalidation. ETags currently use a shared revision, so one account’s mutation can cause other clients to reload their snapshots.
