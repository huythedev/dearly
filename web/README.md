# Dearly web

For guided setup and everyday use, start with the [setup guide](../docs/SETUP.md) and [user guide](../docs/USAGE.md). This page contains the component reference.

React + Vite + TypeScript, sharing the existing FastAPI backend and SQLite database with iOS. Includes signup/login, private journals with excerpt/full sharing previews, anonymous community stories and responses, listening/hiding/reporting, consent-based companions, live chat/history, shared gardens/check-ins/pauses/archives, profile editing, and permission-gated moderation/account/audit screens. Layouts adapt to phones and desktops. English is the source/default language; Vietnamese and System/Light/Dark preferences persist locally. User-written content is never translated.

## Separate frontend Docker image

The frontend is **`dearly-web:latest`**, built from `web/Dockerfile`. Node builds React; the runtime is non-root Nginx, with no backend process or database. The backend image is built separately from `backend/Dockerfile`.

From the repository root:

```bash
python3 configure-docker.py  # Windows: py -3 configure-docker.py
# Or copy .env.example to .env and edit it.
docker compose up -d --build
```

The wizard asks for both published ports and the backend address. By default, web is at **http://127.0.0.1:8003** and API at **http://127.0.0.1:8002**. The frontend's `DEARLY_BACKEND_ADDRESS` defaults to `backend:8002` (the Compose service and internal API port). To use another backend, set the reachable IP/hostname:port, optionally with `http://` or `https://`:

```dotenv
DEARLY_FRONTEND_PORT=9080
DEARLY_BACKEND_PORT=9100
DEARLY_BACKEND_ADDRESS=192.168.1.20:9100
```

This example connects to a backend on another machine. Publish that backend on its LAN interface using `DEARLY_BACKEND_BIND=0.0.0.0` (or a specific LAN IP). For the Compose backend on the same Docker network, use `backend:8002`, regardless of its published host port. For the Docker host, use `host.docker.internal:9100`; Compose configures the Linux host-gateway mapping, and Docker Desktop supports this host as well. `localhost` inside the frontend container refers to that container.

Both published ports and internal listen ports can be customized independently through `.env.example`. After changing settings, run `docker compose up -d frontend` or `docker compose up -d backend` for the affected service; Compose recreates it with the new configuration. Changing the backend address does **not** require rebuilding the frontend image.

Run only one service with `docker compose up -d --build frontend` or `docker compose up -d --build backend`. There is no forced dependency, so each can run on a different host.

### Standalone / interactive frontend startup

```bash
# Repository root
docker build -t dearly-web:latest web
# Prompts for the backend IP/hostname:port:
docker run --rm -it -p 127.0.0.1:9080:8003 dearly-web:latest
```

For detached startup, supply the address explicitly:

```bash
docker run -d --name dearly-web --restart unless-stopped --init -p 127.0.0.1:9080:8003 -e DEARLY_BACKEND_ADDRESS=192.168.1.20:9100 dearly-web:latest
```

For a custom internal frontend port, also set `-e DEARLY_FRONTEND_LISTEN_PORT=8181` and publish `-p 127.0.0.1:9080:8181`. For a host-native backend on Linux, add `--add-host host.docker.internal:host-gateway` and use that hostname. Backend URLs reject credentials, paths, queries, whitespace, and invalid ports. HTTPS upstreams require trusted certificates; their configured hostname is preserved for TLS validation even when a Linux hosts mapping supplies an IP.

### Public domain and routes

The **Oracle_VPS** Cloudflare Tunnel route for **dearly.huythedev.com** uses `http://127.0.0.1:8003`, the frontend published port. The frontend proxies API and WebSocket requests to `backend:8002` by default. Update the tunnel origin if you customize the frontend published port. iOS uses `https://dearly.huythedev.com` through this same route. No Caddy is required.

| Route | Handler |
|---|---|
| `/`, `/journal`, `/community`, `/companion`, `/garden`, `/settings`, `/management` | Nginx serves React SPA |
| `/assets/*`, `/favicon.svg` | Frontend build assets |
| `/v1/*`, `/ws/*` | Forwarded to the configured FastAPI backend, including WebSocket upgrades |
| `/health`, `/docs`, `/openapi.json` | Forwarded to the backend |
| `/frontend-health` | Frontend-only liveness; independent of backend availability |

Browser requests still use relative `/v1/...` and the current origin's `/ws/chat`. Nginx preserves Host including the public port, Origin, cookies, authorization, and WebSocket upgrades. This keeps same-origin session/CSRF checks working across independent backend hosts without browser CORS or exposing an internal backend IP in client code. DNS-based upstreams are refreshed; Linux /etc/hosts mappings such as host-gateway are honored at startup. Only the configured backend origin is proxied.

Missing API/asset routes return 404 rather than SPA HTML. Authenticated responses remain no-store, the HTML shell is no-cache, and hashed assets are cached. No service worker caches private content. For non-Docker local development, Vite proxying and optional FastAPI build serving remain available.

## Local development

Start the backend at `127.0.0.1:8002` using [its setup instructions](../backend/README.md), then from `web/`:

```bash
npm ci
npm run dev
```

Open **http://127.0.0.1:8003**. Vite proxies `/v1`, `/ws` (with WebSocket upgrades), and `/health` to the backend, preserving Host/Origin for the same-origin checks. Use one consistent hostname throughout login. When changing the backend port, update `vite.config.ts`'s development proxy. Production uses the independently configured Nginx frontend and FastAPI backend.

## Browser sessions and chat

Web auth sends `X-Dearly-Client: web` to the existing `/v1/auth/register` or `/v1/auth/login`. It receives an HttpOnly, SameSite=Strict session cookie; HTTPS also sets Secure, including HTTPS terminated at a same-host Cloudflare Tunnel. The body contains `userID` and `expiresAt`, with no token. Tokens never go in localStorage, sessionStorage, a URL, or JavaScript state. Only language/appearance preferences are stored locally. Reload restores the cookie session; logout revokes it server-side and clears the cookie.

Cookie-authenticated writes require the custom web header and same-origin checks. Cookies use `credentials: same-origin`; no CORS middleware is installed. Native clients keep their bearer token contract and Keychain storage.

`/ws/chat` authenticates with a first `{ "type": "authenticate" }` frame plus the browser cookie. Chat sends include a request UUID; replies acknowledge the committed mutation. New messages go only to active, eligible connection members, including messages originating from the existing iOS REST client. The UI deduplicates by message ID, reconnects with backoff, reconciles state on reconnect, and falls back to REST using the **same** request UUID when the socket reply is lost. Private messages remain memory-only. Visible tabs also reconcile state every 15 seconds and on invalidation/online/visibility changes. This is a single-worker pilot; the hub is not a cross-process message broker.

## Checks

```bash
npm test
npm run build
npm audit
```

Desktop/mobile browser flows run in CI after the build and backend dependency installation:

```bash
npx playwright install chromium
npm run test:e2e
```

By default, the browser fixture launches FastAPI against an ignored test database at `backend/data/e2e.sqlite3`. Set `DEARLY_E2E_BASE_URL` only when testing an existing disposable instance; the Docker CI job uses it to test the real frontend proxy on custom ports. `web/scripts/docker-smoke.mjs` also verifies live chat, cookie/CSRF behavior, and REST retry idempotency through the proxy. Tests use unique accounts and synthetic text. Do not point these tests at a production database. The backend suite additionally checks cookie/CSRF boundaries, SPA routing, member-only chat delivery, idempotency across WebSocket/REST, and revocation/size handling.

The iOS project is at `ios/Dearly.xcodeproj`. The updated iOS client receives WebSocket events, keeps idempotent REST sends, and uses REST polling as a fallback. Existing iOS clients still work against the same bearer API.
