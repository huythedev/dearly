# Dearly backend 0.4

A Python 3.11+ / FastAPI / SQLite backend for the Dearly iOS app. It runs as a single server on macOS, Linux, or Windows. No separate database server, Redis, Node.js, or Docker is required.

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

`run.py serve` listens on **`127.0.0.1:8000`** by default. Stop it with **Ctrl+C**.

- Health: `http://127.0.0.1:8000/health`
- Interactive API docs: `http://127.0.0.1:8000/docs`

### Port conflicts and LAN access

The launcher uses the requested port and **does not automatically switch ports**. If port 8000 is already occupied, stop the other service or choose a different port:

```bash
.venv/bin/python run.py serve --port 8001
```

To allow a physical iPhone or another computer on your LAN to connect:

```bash
.venv/bin/python run.py serve --host 0.0.0.0 --port 8000
```

On Windows, use `.\.venv\Scripts\python.exe` in place of `.venv/bin/python` in these and subsequent commands. When changing the port, also update the app’s server URL and any reverse proxy configuration.

### Database location

SQLite is created automatically at `data/dearly.sqlite3`, relative to the working directory. Running from `backend` therefore creates `backend/data/dearly.sqlite3`.

For a service, use an absolute path through `--db` or the `DEARLY_DB` environment variable. Global `--db` must appear **before** the subcommand:

```bash
.venv/bin/python run.py --db /absolute/path/dearly.sqlite3 serve --port 8000
```

Administration commands must use the same database path as the running server. Virtual environments, local databases, and backups are excluded by the repository’s `.gitignore`.

## Connect the iOS app

The app’s default server is **`https://dearly.huythedev.com`**. This is a client default; running the local backend does not configure DNS, TLS, or deployment for that domain. Previously saved server addresses and sessions keep their existing server URL.

1. Open `Dearly.xcodeproj`, select the **Dearly** scheme, and run a **Debug** build on a simulator or iPhone.
2. On the login screen, expand **Server connection / Kết nối server** to choose your backend.
3. For a simulator on the same Mac, enter `http://localhost:8000`.
4. For a physical iPhone, use the computer’s LAN IP, such as `http://192.168.1.10:8000`. Bind the backend to `0.0.0.0`, connect both devices to the same Wi-Fi, and allow Local Network access if prompted. Do not use `localhost` to reach your computer from an iPhone.
5. Register or log in. Usernames use 3–64 characters from `a-z A-Z 0-9 _ . -`; passwords use 10–128 characters; nicknames allow up to 40 characters.
6. To test matching and chat, create two accounts on separate devices or simulators and verify their birth dates with the administration CLI below.

The app requires a backend session and has no offline demo fallback. New accounts can write journals immediately; matching requires operator-verified age. While the app is open, changes normally synchronize about every 3 seconds. Choose English or Vietnamese from the login screen’s language menu or account settings.

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

Registration supports ages 16–100. Age is calculated using the UTC date and checked again when sending or accepting invitations, sending messages, and checking in. Under-18 accounts can connect only with other under-18 accounts at most one year apart. Adults form a separate group. Regular users and moderators cannot set `ageVerified` or change birth dates. Only an admin using the staff API or an operator using the CLI can record a reviewed birth date.

Reports are stored on the server. `reports` lists up to 100 open reports for an operator with host access. `suspend` revokes sessions and ends connections while retaining garden rewards. `restore --username USERNAME` re-enables login without restoring old sessions or connections. The iOS staff console supports manual report review; automatic message filtering and an appeals workflow are not implemented.

### Roles and the in-app staff console

| Role | Permissions |
|---|---|
| `user` | Standard Dearly features; no staff endpoints |
| `moderator` | `reports.read`, `reports.review`, `reports.hide` |
| `admin` | All moderator permissions plus `users.read`, `users.suspend`, `users.verify_age`, `roles.manage`, `audit.read` |

Staff open **avatar → Dearly management** in the iOS app. Reports can be reopened, marked reviewed, dismissed, or used to withdraw a reported public post. Admins can search accounts by username/nickname prefix, confirm externally reviewed birth dates, suspend/restore non-admin accounts, assign/remove moderators, and inspect the audit log. Every mutation requires a reason. Each list uses bounded pagination (30 records by default, at most 50); the app retains only the displayed page.

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

Use the previous checkout's backup command before upgrading. Stop the old backend, update/install the pinned requirements, then restart. Startup migrates SQLite v1/v2 to `user_version=3` in a transaction. It preserves accounts, sessions, journal bodies, reports, connections, and rewards; reconstructs durable sharing restrictions from earlier staff hide audit events; and cancels old pending anonymous invitations to close the identity oracle. Identified invitations are retained. Update the iOS client too: anonymous stories now offer **Hide this story**, with invitations/account blocking available through identified profiles. Repeated startup/CLI access is safe. The default single-worker SQLite setup is unchanged. Do not run the old backend against an upgraded database; rollback requires the pre-upgrade backup and matching code.

### Backups

Use the CLI’s SQLite backup operation rather than copying only the `.sqlite3` file while WAL is active. Choose a new output filename for each backup; the command refuses to overwrite an existing file. Backups contain user data and should be accessible only to operators.

Keep SQLite on a local disk, not SMB/NFS. Do not run multiple replicas writing to the same file.

## HTTPS hosting

For Internet hosting, run the backend on localhost behind an HTTPS reverse proxy. For example, a Caddy configuration for the app’s default domain is:

```caddyfile
dearly.huythedev.com {
    reverse_proxy 127.0.0.1:8000
}
```

The domain must be under your control and point to the host, with the proxy’s required ports reachable. This configuration is an example, not confirmation that the domain is deployed.

When the reverse proxy runs on the same machine, start the backend with:

```bash
.venv/bin/python run.py serve --proxy-ips 127.0.0.1
```

Trust only the actual proxy IP addresses, not `*`. This lets the rate limiter use the client IP supplied by that proxy. Forwarded headers are not trusted by default.

Alternatively, the launcher accepts `--cert certificate.pem --key private-key.pem` after `serve` to terminate TLS directly. Both options are required together. Keep keys and credentials out of version control.

## Docker

Install Docker Engine with the Compose plugin, or Docker Desktop, before using these commands.

### Compose (from the repository root)

```bash
# Optional: copy .env.example to .env and edit the host binding or port.
docker compose up -d --build
docker compose ps
docker compose logs -f backend
```

This builds the local **`dearly-api:latest`** image, starts the backend at `http://127.0.0.1:8000`, and stores SQLite in a named volume. The service restarts unless explicitly stopped. The image runs as a non-root user and checks `/health` every 30 seconds; `docker compose ps` displays its health status.

If port 8000 is occupied, set `DEARLY_PORT=8001` in a root `.env` file before starting. For LAN access, set `DEARLY_BIND=0.0.0.0`. Otherwise the port is accessible only on the Docker host. Update the app’s server URL to match. The container’s internal port remains 8000.

```bash
docker compose exec backend python run.py reports
docker compose exec backend python run.py verify-age --username alice --birth-date 2009-01-01
docker compose exec backend python run.py backup --output /data/dearly-backup.sqlite3
docker compose cp backend:/data/dearly-backup.sqlite3 ./dearly-backup.sqlite3
docker compose down
```

`docker compose down` preserves the database volume. **Adding `--volumes` deletes that volume and its data.** Use a new backup filename for each backup. Do not run the native backend and Compose on the same host port.

### Build and run without Compose (from `backend`)

```bash
docker build -t dearly-api:latest .
docker run -d --name dearly-api --restart unless-stopped --init -p 127.0.0.1:8000:8000 -v dearly-data:/data dearly-api:latest
docker logs -f dearly-api
```

To avoid a host port conflict, change the mapping to `127.0.0.1:8001:8000`. Run administration commands with `docker exec dearly-api python run.py reports`. Stop the container with `docker stop dearly-api`.

The build context includes only the Dockerfile, runtime Python files, and dependency manifest. Local databases, credentials, virtual environments, and tests are excluded from the image. The image does not configure public DNS or HTTPS; use a reverse proxy as described above.

Docker is not installed on the current development machine, so the image build and container health check have not yet been verified here.

## Tests

From `backend` on macOS/Linux:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python benchmark.py
```

On Windows, use `.\.venv\Scripts\python.exe`. The benchmark starts a real HTTP server on a temporary localhost port and removes its temporary fixture data afterward. This temporary-port behavior belongs to the benchmark; the normal server launcher does not choose a free port automatically.

The backend suite covers staff authorization, migration, the audit regressions, and real HTTP upload admission/timeouts. See the [validation notes](../docs/VALIDATION.md). GitHub Actions runs backend/static/dependency checks and native iOS tests. Windows/macOS backend execution and Docker have not been verified locally.

## Runtime behavior and limits

- Uvicorn uses standard `asyncio` and `h11`, with one worker and a concurrency limit of 64. Synchronous endpoints use up to 16 threads, and password hashing allows at most two simultaneous operations.
- SQLite uses WAL, indexes for common queries, and `BEGIN IMMEDIATE` transactions for invitation and check-in consistency. There is one writer at a time, with a 2 MiB cache per connection.
- Request bodies are limited to 128 KiB and expire after 5 seconds without a chunk or 15 seconds total. At most 32 bodies can be read concurrently, at most 8 per client IP; excess uploads receive 429 before parsing/authentication, leaving capacity for body-free reads/health. Timeouts return 408 and close the connection. The launcher supports `--body-idle-timeout SECONDS` and `--body-total-timeout SECONDS`. Keep proxy/header deadlines and origin access restrictions as well; these application controls start after HTTP headers are received.
- Journals are limited to 20,000 characters; messages to 4,000; responses to 2,000. The rate limiter holds at most 4,096 buckets in memory.
- State snapshots return bounded windows: up to 60 personal journals, 60 community posts, 60 companion journals, 20 recent gardens plus the active connection if needed, 100 invitations, 200 responses, and 100 recent messages.
- Personal journal pagination uses 40 entries per page in the app, with an API maximum of 60. Saved gardens use 20 per page (API maximum 50) with member profiles included. Chat supports up to 100 messages per API page; the app retains at most 500 messages in memory. Community and companion journal screens show the latest window without older-history navigation.
- The app polls about every 3 seconds in the foreground. ETag/304 responses avoid resending unchanged state; failed requests increase the delay up to 30 seconds. There is no push delivery or WebSocket connection while the app is closed.
- Mutations use request UUIDs. Results are stored in the same transaction so retrying a request does not duplicate a message. Retry keys are retained for 7 days; daily check-ins have a separate UTC uniqueness constraint.
- Passwords use salted PBKDF2-SHA256 with 600,000 iterations. Random bearer tokens are stored only as hashes on the server, expire after 30 days, and are kept in Keychain on iOS. App session state stays in memory rather than being written to a local journal/chat cache.

This design targets a small, controlled pilot. Larger write volumes or multiple replicas require a server database and more targeted cache invalidation. ETags currently use a shared revision, so one account’s mutation can cause other clients to reload their snapshots.
