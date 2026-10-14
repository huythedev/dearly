# Dearly backend 0.2

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

The app’s default server is **`https://api.dearly.huythedev.com`**. This is a client default; running the local backend does not configure DNS, TLS, or deployment for that domain. Previously saved server addresses and sessions keep their existing server URL.

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

Registration supports ages 16–100. Age is calculated using the UTC date and checked again when sending or accepting invitations, sending messages, and checking in. Under-18 accounts can connect only with other under-18 accounts at most one year apart. Adults form a separate group. Clients cannot set `ageVerified` or change birth dates through the API.

Reports are stored on the server. `reports` lists up to 100 open reports for an operator with host access. `suspend` revokes sessions and ends connections while retaining garden rewards. There is no moderator dashboard, automatic message filter, or appeals system.

### Backups

Use the CLI’s SQLite backup operation rather than copying only the `.sqlite3` file while WAL is active. Choose a new output filename for each backup; the command refuses to overwrite an existing file. Backups contain user data and should be accessible only to operators.

Keep SQLite on a local disk, not SMB/NFS. Do not run multiple replicas writing to the same file.

## HTTPS hosting

For Internet hosting, run the backend on localhost behind an HTTPS reverse proxy. For example, a Caddy configuration for the app’s default domain is:

```caddyfile
api.dearly.huythedev.com {
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

## Optional Docker setup

Run from `backend`:

```bash
docker build -t dearly-api .
docker run --rm --name dearly-api -p 127.0.0.1:8000:8000 -v dearly-data:/data dearly-api
```

The container runs as a non-root user and stores SQLite in `/data`. The named volume preserves data across container restarts. To avoid a host port conflict, change the mapping to `127.0.0.1:8001:8000`. Change the host binding if LAN access is required.

Run administration commands against the container’s database with, for example:

```bash
docker exec dearly-api python run.py reports
```

## Tests

From `backend` on macOS/Linux:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python benchmark.py
```

On Windows, use `.\.venv\Scripts\python.exe`. The benchmark starts a real HTTP server on a temporary localhost port and removes its temporary fixture data afterward. This temporary-port behavior belongs to the benchmark; the normal server launcher does not choose a free port automatically.

The [historical validation notes](../docs/VALIDATION.md) record 21 passing backend tests on Linux. Local setup and a server health check were also verified on macOS. Windows and Docker execution have not been verified in this session. No GitHub Actions workflows are included in this checkout.

## Runtime behavior and limits

- Uvicorn uses standard `asyncio` and `h11`, with one worker and a concurrency limit of 64. Synchronous endpoints use up to 16 threads, and password hashing allows at most two simultaneous operations.
- SQLite uses WAL, indexes for common queries, and `BEGIN IMMEDIATE` transactions for invitation and check-in consistency. There is one writer at a time, with a 2 MiB cache per connection.
- Request bodies are limited to 128 KiB; journals to 20,000 characters; messages to 4,000; responses to 2,000. The rate limiter holds at most 4,096 buckets in memory.
- State snapshots return bounded windows: up to 60 personal journals, 60 community posts, 60 companion journals, 20 gardens, 100 invitations, 200 responses, and 100 recent messages.
- Personal journal pagination uses 40 entries per page in the app, with an API maximum of 60. Chat supports up to 100 messages per API page; the app retains at most 500 messages in memory. Community and companion journal screens show the latest window without older-history navigation.
- The app polls about every 3 seconds in the foreground. ETag/304 responses avoid resending unchanged state; failed requests increase the delay up to 30 seconds. There is no push delivery or WebSocket connection while the app is closed.
- Mutations use request UUIDs. Results are stored in the same transaction so retrying a request does not duplicate a message. Retry keys are retained for 7 days; daily check-ins have a separate UTC uniqueness constraint.
- Passwords use salted PBKDF2-SHA256 with 600,000 iterations. Random bearer tokens are stored only as hashes on the server, expire after 30 days, and are kept in Keychain on iOS. App session state stays in memory rather than being written to a local journal/chat cache.

This design targets a small, controlled pilot. Larger write volumes or multiple replicas require a server database and more targeted cache invalidation. ETags currently use a shared revision, so one account’s mutation can cause other clients to reload their snapshots.
