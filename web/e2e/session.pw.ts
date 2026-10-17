import { expect, test, type WebSocketRoute } from '@playwright/test';
import type { Envelope } from '../src/types';
import fixture from '../src/fixtures/encryption-v1.json' with { type: 'json' };
import { open, recoverIdentity, seal, unb64, type IdentityBundle } from '../src/crypto';

const userID = '33333333-3333-4333-8333-333333333333';
const envelope: Envelope = { serverNow: 813585600, state: {
  currentUserID: userID, profiles: [{ id: userID, nickname: 'Session friend', age: 25, ageVerified: true,
    symbol: 'leaf.fill', bio: '', interests: [], support: 'listen', pace: 'Evenings' }],
  journals: [], messages: [], connections: [], comments: [], invitations: [], suggestedUserIDs: [],
} };

for (const status of [200, 503, 401]) {
  test(`socket rejection validates the current HTTP session (${status}) without losing a valid draft`, async ({ page }) => {
    await page.addInitScript(id => localStorage.setItem(`dearly.guide.v1:${id}`, 'seen'), userID);
    let first!: WebSocketRoute;
    let sockets = 0, reads = 0, validating = false;
    let release!: () => void;
    const held = new Promise<void>(resolve => { release = resolve; });
    await page.routeWebSocket('**/ws/chat', socket => {
      if (++sockets === 1) first = socket;
      socket.onMessage(() => socket.send(JSON.stringify({ type: 'ready' })));
    });
    await page.route('**/v1/journals?*', route => route.fulfill({ json: { items: [], nextCursor: null } }));
    await page.route('**/v1/state', async route => {
      reads++;
      if (validating) await held;
      await route.fulfill(validating && status !== 200 ? { status, json: { detail: 'Synthetic session check' } } : { json: envelope });
    });
    try {
      await page.goto('/journal');
      await expect.poll(() => reads).toBeGreaterThanOrEqual(2);
      await expect(page.getByRole('status')).toHaveText('A little more connected');
      await page.getByRole('button', { name: 'New entry', exact: true }).click();
      const draft = page.getByRole('dialog');
      await draft.getByLabel('Title', { exact: true }).fill('Draft stays here');
      await draft.getByRole('textbox', { name: 'Your words', exact: true }).fill('Unsent words to keep through reconnection.');
      const before = reads;
      validating = true;
      await first.close({ code: 4401, reason: 'Old socket session' });
      await expect.poll(() => reads).toBeGreaterThan(before);
      await expect(draft.getByRole('textbox', { name: 'Your words', exact: true })).toHaveValue('Unsent words to keep through reconnection.');
      release();
      if (status === 401) {
        await expect(page.getByRole('heading', { name: 'Welcome back.' })).toBeVisible();
        await expect(page.getByRole('dialog')).toHaveCount(0);
      } else {
        await expect(draft.getByLabel('Title', { exact: true })).toHaveValue('Draft stays here');
        await expect.poll(() => sockets).toBeGreaterThanOrEqual(2);
        if (status === 503) await expect(page.getByRole('status')).toHaveText('Sync interrupted · retrying');
        else await expect(page.getByRole('status')).toHaveText('A little more connected');
        await expect(page.getByRole('heading', { name: 'Welcome back.' })).toHaveCount(0);
      }
    } finally { release(); }
  });
}

test('a stale socket message rejection retries with the current cookie and original account/key', async ({ page }) => {
  await page.addInitScript(id => localStorage.setItem(`dearly.guide.v1:${id}`, 'seen'), userID);
  const connected: Envelope = { ...envelope, state: { ...envelope.state, connections: [{
    id: fixture.connectionID, members: [userID, fixture.bob.bundle.userID], startedAt: 813585600, endedAt: null,
    paused: false, checkIns: {}, bestStreak: 0, serverTotalDays: 0, serverCurrentStreak: 0,
  }] } };
  let socketKey = '';
  let published!: IdentityBundle;
  let live!: WebSocketRoute;
  await page.routeWebSocket('**/ws/chat', socket => socket.onMessage(raw => {
    live = socket;
    const value = JSON.parse(String(raw));
    if (value.type === 'authenticate') socket.send(JSON.stringify({ type: 'ready' }));
    if (value.type === 'message.send') {
      socketKey = value.requestID;
      socket.send(JSON.stringify({ type: 'error', requestID: value.requestID, status: 401, detail: 'Old socket session' }));
    }
  }));
  let retries = 0;
  await page.route('**/v1/**', async route => {
    if (route.request().url().endsWith('/state')) return route.fulfill({ json: connected });
    if (route.request().url().endsWith('/encryption/identity')) {
      if (route.request().method() === 'GET') return route.fulfill({ status: 404, json: { detail: 'Enable encryption' } });
      const input = route.request().postDataJSON();
      const hash = await crypto.subtle.digest('SHA-256', new Uint8Array([...unb64(input.agreementKey), ...unb64(input.signingKey)]));
      const fingerprint = Array.from(new Uint8Array(hash), n => n.toString(16).padStart(2, '0')).join('');
      published = { ...input, userID, fingerprint };
      return route.fulfill({ json: published });
    }
    if (route.request().url().endsWith(`/encryption/keys/${fixture.bob.bundle.userID}`)) return route.fulfill({ json: fixture.bob.bundle });
    if (route.request().url().endsWith('/actions')) {
      retries++;
      expect(route.request().headers()['x-dearly-user']).toBe(userID);
      expect(route.request().postDataJSON().requestID).toBe(socketKey);
      expect(route.request().postDataJSON().kind).toBe('message.send');
      const { payload } = route.request().postDataJSON();
      expect(payload.text).not.toContain('A hello after reconnecting.');
      const bob = await recoverIdentity(fixture.bob.bundle, fixture.bob.recoveryCode);
      expect(await open(bob, payload.text, 'message', payload.clientID, fixture.connectionID, published)).toEqual({ text: 'A hello after reconnecting.' });
      return route.fulfill({ json: { ok: true, id: 'saved' } });
    }
    return route.fulfill({ json: { items: [], profiles: [], nextCursor: null } });
  });
  await page.goto('/companion');
  await expect(page.getByRole('status')).toHaveText('A little more connected');
  await page.getByLabel('Your message', { exact: true }).fill('A hello after reconnecting.');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect.poll(() => retries).toBe(1);
  await expect(page.getByLabel('Your message', { exact: true })).toHaveValue('');
  await expect(page.getByRole('heading', { name: 'Welcome back.' })).toHaveCount(0);
  const bob = await recoverIdentity(fixture.bob.bundle, fixture.bob.recoveryCode);
  const replyID = crypto.randomUUID().toUpperCase();
  const reply = await seal(bob, 'message', replyID, fixture.connectionID, { text: 'An encrypted reply 🌿' }, [published, bob.bundle]);
  live.send(JSON.stringify({ type: 'message', message: { id: replyID, connectionID: fixture.connectionID, senderID: bob.bundle.userID, text: reply, date: 813585600 } }));
  await expect(page.getByRole('log', { name: 'Conversation' })).toContainText('An encrypted reply 🌿');
});

test('browser login cookies survive a new browser session and logout still revokes them', async ({ page, context, browser }) => {
  await page.goto('/');
  const signup = await context.request.post('/v1/auth/register', { headers: { 'X-Dearly-Client': 'web' },
    data: { username: `persistent_${Date.now()}`, password: 'session-test-password', nickname: 'Persistent friend', birthDate: '2000-01-01' } });
  expect(signup.status()).toBe(201);
  const user = await signup.json();
  const cookies = await context.cookies();
  const session = cookies.find(cookie => cookie.name === 'dearly_session')!;
  expect(session.httpOnly).toBe(true);
  expect(session.sameSite).toBe('Strict');
  expect(session.expires).toBeGreaterThan(Date.now() / 1000 + 29 * 86400);
  // Reopening a browser restores persistent cookies, not session-only cookies.
  const reopened = await browser.newContext({ storageState: { cookies: cookies.filter(cookie => cookie.expires > 0), origins: [] } });
  try {
    const url = new URL('/v1/state', page.url()).href;
    const state = await reopened.request.get(url);
    expect(state.status()).toBe(200);
    expect((await state.json()).state.currentUserID).toBe(user.userID);
    const logout = await reopened.request.post(new URL('/v1/auth/logout', page.url()).href, { headers: { 'X-Dearly-Client': 'web' } });
    expect(logout.status()).toBe(200);
    expect((await context.request.get('/v1/state')).status()).toBe(401);
  } finally { await reopened.close(); }
});
