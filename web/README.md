# Dearly web

React + Vite + TypeScript, sharing the existing FastAPI backend and SQLite database with iOS. Includes signup/login, private journals with excerpt/full sharing previews, anonymous community stories and responses, listening/hiding/reporting, consent-based companions, live chat/history, shared gardens/check-ins/pauses/archives, profile editing, and permission-gated moderation/account/audit screens. Layouts adapt to phones and desktops. English is the source/default language; Vietnamese and System/Light/Dark preferences persist locally. User-written content is never translated.

## Production / one origin

From the repository root:

```bash
docker compose up -d --build
```

Open `http://127.0.0.1:8000`. The image builds `web/dist` and FastAPI serves it. Keep the existing Cloudflare Tunnel routing all requests for `dearly.huythedev.com` to this service. Caddy is not required.

| Route | Handler |
|---|---|
| `/`, `/journal`, `/community`, `/companion`, `/garden`, `/settings`, `/management` | React SPA |
| `/assets/*`, `/favicon.svg` | Built frontend assets |
| `/v1/*` | FastAPI REST |
| `/ws/chat` | Authenticated WebSocket |
| `/health`, `/docs`, `/openapi.json` | FastAPI health and API documentation |

REST requests always use `/v1/...`; sockets derive `ws:`/`wss:` and the host from `location`. There is no API-origin configuration to keep in sync. Missing API/asset routes return 404 rather than SPA HTML. SPA responses use a restrictive content security policy and no-cache; authenticated responses use no-store. No service worker caches private content.

Without Docker, use Node.js 24 to run `npm ci` and `npm run build` in this directory, then start the backend normally. It auto-discovers `web/dist`; Node is not needed at runtime. The backend's `--web-dir` / `DEARLY_WEB_DIST` can select another absolute build directory.

## Local development

Start the backend at `127.0.0.1:8000` using [its setup instructions](../backend/README.md), then from `web/`:

```bash
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. Vite proxies `/v1`, `/ws` (with WebSocket upgrades), and `/health` to the backend, preserving Host/Origin for the same-origin checks. Use one consistent hostname throughout login. When changing the backend port, update `vite.config.ts`'s development proxy. Production remains one FastAPI service.

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

The browser fixture launches the actual FastAPI app against an ignored test database at `backend/data/e2e.sqlite3`. Tests use unique accounts and synthetic text. Do not point these tests at a production database. The backend suite additionally checks cookie/CSRF boundaries, SPA routing, member-only chat delivery, idempotency across WebSocket/REST, and revocation/size handling.

The iOS project is at `ios/Dearly.xcodeproj`. The updated iOS client receives WebSocket events, keeps idempotent REST sends, and uses REST polling as a fallback. Existing iOS clients still work against the same bearer API.
