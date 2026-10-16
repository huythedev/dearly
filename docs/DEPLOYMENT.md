# Host and maintain Dearly

[All guides](README.md) · [First-time setup](SETUP.md) · [Administration](ADMINISTRATION.md)

Run commands from the repository root. Docker builds two independent images: `dearly-web:latest` for the React/Nginx frontend and `dearly-api:latest` for FastAPI. The existing `dearly-data` volume stores SQLite data.

## Custom ports

Copy [`.env.example`](../.env.example) to `.env`, or run the [configuration helper](SETUP.md#choose-your-ports-and-backend).

| Setting | Default | Purpose |
|---|---|---|
| `DEARLY_FRONTEND_PORT` | `8003` | Web port published on the host |
| `DEARLY_BACKEND_PORT` | `8002` | API port published on the host |
| `DEARLY_FRONTEND_LISTEN_PORT` | `8003` | Port inside the frontend container |
| `DEARLY_BACKEND_LISTEN_PORT` | `8002` | Port inside the backend container |
| `DEARLY_BACKEND_ADDRESS` | `backend:8002` | Backend address reachable from the frontend container |
| `DEARLY_FRONTEND_BIND` | `127.0.0.1` | Host interface exposing the web port |
| `DEARLY_BACKEND_BIND` | `127.0.0.1` | Host interface exposing the API port |

For different host ports with the same internal ports:

```dotenv
DEARLY_FRONTEND_PORT=9080
DEARLY_BACKEND_PORT=9100
DEARLY_BACKEND_ADDRESS=backend:8002
```

Open the web app on port **9080**. The frontend still reaches the Compose backend at **`backend:8002`**, not its published host port 9100.

For custom internal ports as well, set `DEARLY_FRONTEND_LISTEN_PORT` and `DEARLY_BACKEND_LISTEN_PORT`. Keep an explicitly configured `DEARLY_BACKEND_ADDRESS` aligned with the backend's internal port; for example, `backend:8200` when the backend listens on 8200.

Apply changes with `docker compose up -d`. Changing ports or backend address recreates the affected containers without rebuilding the frontend image. Existing `.env` settings are retained; review them when adopting new defaults. Legacy `DEARLY_PORT` and `DEARLY_BIND` still provide backend host-port/bind fallbacks when the newer settings are absent.

## Frontend and backend on separate machines

On the backend host, expose the API on a reachable LAN interface. For example:

```dotenv
DEARLY_BACKEND_BIND=0.0.0.0
DEARLY_BACKEND_PORT=8002
```

Start only that service:

```bash
docker compose up -d --build backend
```

On the frontend host, set the backend's reachable IP/hostname and published port:

```dotenv
DEARLY_BACKEND_ADDRESS=192.168.1.20:8002
```

Then start only the frontend:

```bash
docker compose up -d --build frontend
```

Use an address reachable **from the frontend container**. `localhost` inside it refers to that container. For a backend on the Docker host, use `host.docker.internal:8002`; Compose supplies the Linux host-gateway mapping. HTTP is assumed unless you specify `https://`; HTTPS upstreams need a trusted certificate. Use a secured backend endpoint for traffic beyond a trusted private network.

### Standalone images and interactive startup

```bash
docker build -t dearly-web:latest web
docker run --rm -it -p 127.0.0.1:8003:8003 dearly-web:latest
```

The frontend asks for the backend IP/hostname:port. For detached startup, supply `-e DEARLY_BACKEND_ADDRESS=192.168.1.20:8002`. On Linux, a standalone container using `host.docker.internal` also needs `--add-host host.docker.internal:host-gateway`.

Build the API independently with `docker build -t dearly-api:latest backend`. See the [backend Docker reference](../backend/README.md#without-compose-repository-root) and [frontend reference](../web/README.md#standalone--interactive-frontend-startup) for full `docker run` examples.

## Public domain and Cloudflare Tunnel

For Dearly's `Oracle_VPS` deployment, use one public hostname route:

| Tunnel field | Value |
|---|---|
| Hostname | `dearly.huythedev.com` |
| Path | Leave empty to include all paths |
| Service | `http://127.0.0.1:8003` |

This assumes the tunnel connector runs on the same host and can reach that loopback address. If your connector runs in another container or on another machine, use the frontend address reachable from that connector.

Nginx serves React at `/` and static assets, and forwards `/v1/*`, `/ws/*`, `/health`, `/docs`, and `/openapi.json` to the configured backend. **No separate tunnel route for `/v1` or `/ws/chat` is needed.** Update the tunnel origin when changing the frontend's published port. No additional Caddy server is required.

Browsers use relative API paths; iOS uses the public HTTPS origin, with WebSocket chat on the corresponding `wss://` origin. The frontend preserves Host (including a public port), Origin, cookies, authorization, and WebSocket upgrades. The backend remains shared between iOS and web.

Forwarded client IPs are ignored by default. If enabling `DEARLY_PROXY_IPS`, trust only the actual proxy addresses and account for the whole tunnel/proxy chain. See [HTTPS hosting](../backend/README.md#https-hosting) for the trust boundary and request limits.

## Updates and backups

Keep the same Compose project/directory so the existing data volume is reused. Back up with the currently installed version before upgrading. Use a new backup filename each time; the CLI refuses to overwrite one.

```bash
docker compose exec backend python run.py backup --output /data/dearly-before-update.sqlite3
docker compose cp backend:/data/dearly-before-update.sqlite3 ./dearly-before-update.sqlite3
docker compose stop backend
git pull --ff-only
docker compose up -d --build
```

This briefly stops the API while you update. The SQLite backup command makes a consistent copy while the database is live; copying only the active `.sqlite3` file can miss WAL data. Keep backups accessible only to operators.

Database upgrades run on startup and preserve accounts, sessions, journal text, connections, and rewards. Review [upgrade compatibility](../backend/README.md#upgrading-an-existing-database) before updating an older installation. Update the iOS app and backend together when adopting the English support identifiers. A rollback requires the matching earlier code and its pre-upgrade database backup.

For frontend-only code changes, pull the update and run `docker compose up -d --build frontend`. For runtime backend-address changes, `docker compose up -d frontend` is sufficient.

## Logs and stopping

```bash
docker compose ps
docker compose logs -f frontend backend
docker compose down
```

`down` stops the app and preserves its data volume. Adding `--volumes` deletes that volume and its data. Keep SQLite on local disk rather than SMB/NFS, and use the documented single backend worker. Runtime limits and scaling notes are in the [backend reference](../backend/README.md#runtime-behavior-and-limits).
