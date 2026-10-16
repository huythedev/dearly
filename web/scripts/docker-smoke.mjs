// Integration checks against disposable CI containers, including native WebSocket clients.
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const origin = process.env.DEARLY_TEST_FRONTEND_URL ?? 'http://127.0.0.1:8003';
const backend = process.env.DEARLY_TEST_BACKEND_URL ?? 'http://127.0.0.1:8002';
const options = () => ({ signal: AbortSignal.timeout(5000) });
for (let attempt = 0; ; attempt++) {
  try {
    const response = await fetch(`${origin}/health`, { signal: AbortSignal.timeout(1000) });
    if (response.ok) break;
  } catch {}
  if (attempt >= 40) throw new Error('Frontend cannot reach the configured backend.');
  await new Promise(resolve => setTimeout(resolve, 500));
}

async function json(path, init = {}) {
  const response = await fetch(`${origin}${path}`, { ...options(), ...init,
    headers: { 'Content-Type': 'application/json', ...init.headers } });
  const value = await response.json();
  assert.ok(response.ok, JSON.stringify(value));
  return { response, value };
}
const html = await fetch(origin, options());
const document = await html.text();
assert.match(document, /Dearly/);
const assetPath = document.match(/(?:src|href)="(\/assets\/[^\"]+\.(?:js|css))"/)?.[1];
assert.ok(assetPath, 'The build must reference a fingerprinted asset.');
const asset = await fetch(`${origin}${assetPath}`, options());
assert.equal(asset.status, 200);
assert.match(asset.headers.get('Cache-Control') ?? '', /max-age=604800/);
assert.match(html.headers.get('Content-Security-Policy'), /connect-src 'self'/);
assert.equal((await fetch(`${origin}/journal`, options())).status, 200);
assert.equal((await fetch(`${origin}/assets/missing.js`, options())).status, 404);
assert.equal((await fetch(`${origin}/assets/.hidden.js`, options())).status, 404);
assert.equal((await fetch(`${origin}/v1/missing`, options())).status, 404);
assert.equal((await fetch(`${backend}/`, options())).status, 404, 'Backend image must remain API-only.');
assert.equal((await fetch(`${backend}/health`, options())).status, 200);

const suffix = randomUUID().slice(0, 8);
const password = 'container-test-password';
async function account(name) {
  const username = `${name}_${suffix}`;
  const { value } = await json('/v1/auth/register', { method: 'POST', body: JSON.stringify({ username, password, nickname: name, birthDate: '2000-01-01' }) });
  execFileSync('docker', ['compose', 'exec', '-T', 'backend', 'python', 'run.py', 'verify-age', '--username', username, '--birth-date', '2000-01-01'], { stdio: 'pipe' });
  return { ...value, username, headers: { Authorization: `Bearer ${value.token}` } };
}
const first = await account('socket_a');
const second = await account('socket_b');
async function action(user, kind, payload, requestID = randomUUID()) {
  return (await json('/v1/actions', { method: 'POST', headers: user.headers, body: JSON.stringify({ requestID, kind, payload }) })).value;
}
const invitation = await action(first, 'invitation.send', { userID: second.userID });
const connection = await action(second, 'invitation.accept', { id: invitation.id });

function connect(token) {
  const socket = new WebSocket(origin.replace(/^http/, 'ws') + '/ws/chat');
  const frames = [];
  socket.addEventListener('open', () => socket.send(JSON.stringify({ type: 'authenticate', token })));
  socket.addEventListener('message', event => frames.push(JSON.parse(event.data)));
  return { socket, async receive(type) {
    for (let i = 0; i < 100; i++) {
      const index = frames.findIndex(frame => frame.type === type);
      if (index >= 0) return frames.splice(index, 1)[0];
      if (socket.readyState === WebSocket.CLOSED) throw new Error('Socket closed before expected frame.');
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error(`Missing socket frame: ${type}`);
  } };
}
const a = connect(first.token), b = connect(second.token);
try {
  await a.receive('ready'); await b.receive('ready');
  const requestID = randomUUID();
  const payload = { connectionID: connection.id, text: 'Live message through the separate frontend proxy.' };
  a.socket.send(JSON.stringify({ type: 'message.send', requestID, ...payload }));
  const ack = await a.receive('ack');
  const delivered = await b.receive('message');
  assert.equal(delivered.message.text, payload.text);
  assert.equal(ack.result.id, delivered.message.id);
  const replay = await action(first, 'message.send', payload, requestID);
  assert.equal(replay.id, ack.result.id);
} finally { a.socket.close(); b.socket.close(); }

const login = await json('/v1/auth/login', { method: 'POST', headers: { Origin: origin, 'X-Dearly-Client': 'web' }, body: JSON.stringify({ username: first.username, password }) });
assert.equal(login.value.token, undefined);
const cookie = login.response.headers.get('set-cookie').split(';')[0];
assert.match(login.response.headers.get('set-cookie'), /HttpOnly/i);
const state = await json('/v1/state', { headers: { Cookie: cookie } });
assert.equal(state.value.state.currentUserID, first.userID);
assert.equal(state.value.state.messages.length, 1);
const crossOrigin = await fetch(`${origin}/v1/auth/logout`, { ...options(), method: 'POST', headers: { Cookie: cookie, Origin: 'http://evil.example', 'X-Dearly-Client': 'web' } });
assert.equal(crossOrigin.status, 403);
await json('/v1/auth/logout', { method: 'POST', headers: { Cookie: cookie, Origin: origin, 'X-Dearly-Client': 'web' } });
assert.equal((await fetch(`${origin}/v1/state`, { ...options(), headers: { Cookie: cookie } })).status, 401);
console.log('Separate frontend/backend: ports, SPA, cookies, CSRF, REST and live WebSocket delivery passed.');
