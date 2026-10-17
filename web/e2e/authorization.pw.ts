import { expect, test, type Page } from '@playwright/test';
import type { Envelope, Role } from '../src/types';

const userID = '66666666-6666-4666-8666-666666666666';
const moderator = ['reports.read', 'reports.review', 'reports.hide', 'users.read', 'users.verify_age'];
const admin = [...moderator, 'roles.manage', 'users.suspend', 'audit.read'];
const member = { id: '77777777-7777-4777-8777-777777777777', username: 'private_member', nickname: 'Sensitive account nickname',
  role: 'user', suspended: false, ageVerified: false, birthDate: '2000-01-01' };

async function fixture(page: Page, role: Role | undefined = 'admin', permissions = admin) {
  const envelope: Envelope = { serverNow: 813585600, state: {
    currentUserID: userID, currentUserRole: role, permissions,
    profiles: [{ id: userID, nickname: 'Reviewer', age: 25, ageVerified: true, symbol: 'leaf.fill', bio: '', interests: [], support: 'listen', pace: 'Evenings' }],
    journals: [], messages: [], connections: [], comments: [], invitations: [], suggestedUserIDs: [],
  } };
  const control = { envelope, stateStatus: 200, accessStatus: 200, dataStatus: 200, actionStatus: 200,
    accessUserID: userID, accessReads: 0, dataReads: 0, actions: 0, hold: Promise.resolve(), changed: () => {} };
  await page.addInitScript(id => localStorage.setItem(`dearly.guide.v1:${id}`, 'seen'), userID);
  await page.routeWebSocket('**/ws/chat', socket => {
    control.changed = () => socket.send(JSON.stringify({ type: 'state.changed' }));
    socket.onMessage(() => socket.send(JSON.stringify({ type: 'ready' })));
  });
  await page.route('**/v1/**', async route => {
    const url = new URL(route.request().url());
    const error = (status: number) => route.fulfill({ status, json: { detail: 'You do not have access to management.' } });
    if (url.pathname === '/v1/state') return control.stateStatus === 200 ? route.fulfill({ json: envelope }) : error(control.stateStatus);
    if (url.pathname === '/v1/staff/access') {
      control.accessReads++;
      expect(route.request().headers()['x-dearly-user']).toBe(userID);
      await control.hold;
      if (control.accessStatus !== 200) return error(control.accessStatus);
      return route.fulfill({ json: { userID: control.accessUserID, currentUserRole: envelope.state.currentUserRole, permissions: envelope.state.permissions } });
    }
    if (url.pathname.startsWith('/v1/staff/')) {
      control.dataReads++;
      expect(route.request().headers()['x-dearly-user']).toBe(userID);
      if (control.dataStatus !== 200) return error(control.dataStatus);
      return route.fulfill({ json: { items: url.pathname.endsWith('/users') ? [member] : [], nextCursor: url.pathname.endsWith('/users') ? 'next-page' : null } });
    }
    if (url.pathname === '/v1/actions') { control.actions++; return error(control.actionStatus); }
    return route.fulfill({ json: { items: [], nextCursor: null } });
  });
  return control;
}

async function enterManagement(page: Page) {
  await page.goto('/settings');
  await page.locator('.account-actions').getByRole('button', { name: 'Management', exact: true }).click();
}

for (const role of ['user', undefined] as const) {
  test(`member or legacy snapshots cannot expose management through stale grants (${role ?? 'missing role'})`, async ({ page }) => {
    const control = await fixture(page, role);
    if (role === undefined) delete control.envelope.state.currentUserRole;
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Your space, your pace.' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Management', exact: true })).toHaveCount(0);
    await page.evaluate(() => { history.pushState({}, '', '/management'); dispatchEvent(new PopStateEvent('popstate')); });
    await expect(page.getByText('You do not have access to management.', { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Dearly management', exact: true })).toHaveCount(0);
    expect(control.accessReads).toBe(0); expect(control.dataReads).toBe(0);
  });
}

test('staff controls and reads wait for a fresh authorization response', async ({ page }) => {
  const control = await fixture(page);
  let release!: () => void;
  control.hold = new Promise(resolve => { release = resolve; });
  try {
    await enterManagement(page);
    await expect(page.getByText('Checking management access…', { exact: true })).toBeVisible();
    await expect.poll(() => control.accessReads).toBe(1);
    expect(control.dataReads).toBe(0);
    await expect(page.getByRole('button', { name: 'Accounts', exact: true })).toHaveCount(0);
    release();
    await expect(page.getByRole('heading', { name: 'Dearly management', exact: true })).toBeVisible();
    await expect.poll(() => control.dataReads).toBe(1);
  } finally { release(); }
});

test('a stale staff snapshot cannot open management when the server denies access', async ({ page }) => {
  const control = await fixture(page);
  control.accessStatus = 403;
  await enterManagement(page);
  await expect(page.getByRole('alert')).toContainText('You do not have access to management.');
  expect(control.dataReads).toBe(0);
  await expect(page.getByRole('heading', { name: 'Dearly management', exact: true })).toHaveCount(0);
});

test('an authorization response for another account cannot open management', async ({ page }) => {
  const control = await fixture(page);
  control.accessUserID = member.id;
  await enterManagement(page);
  await expect(page.getByRole('alert')).toContainText('You do not have access to management.');
  expect(control.dataReads).toBe(0);
});

test('demotion closes an already-open role change form and removes admin controls', async ({ page }) => {
  const control = await fixture(page);
  await enterManagement(page);
  await page.getByRole('button', { name: 'Accounts', exact: true }).click();
  await page.getByRole('button', { name: 'Change role', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Change role', exact: true })).toBeVisible();
  control.envelope.state.currentUserRole = 'moderator'; control.envelope.state.permissions = moderator;
  control.changed();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: 'Accounts', exact: true }).click();
  for (const name of ['Change role', 'Suspend account', 'Audit log']) await expect(page.getByRole('button', { name, exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Verify age', exact: true })).toBeVisible();
  expect(control.actions).toBe(0);
});

for (const trigger of ['pagination', 'action'] as const) {
  test(`a staff ${trigger} denial clears private data and dialogs even when snapshot sync fails`, async ({ page }) => {
    const control = await fixture(page);
    await enterManagement(page);
    await page.getByRole('button', { name: 'Accounts', exact: true }).click();
    await expect(page.getByRole('heading', { name: member.nickname, exact: true })).toBeVisible();
    control.stateStatus = 503;
    if (trigger === 'pagination') {
      control.dataStatus = 403;
      await page.getByRole('button', { name: 'More accounts', exact: true }).click();
    } else {
      control.actionStatus = 403;
      await page.getByRole('button', { name: 'Change role', exact: true }).click();
      const dialog = page.getByRole('dialog');
      await dialog.getByLabel('Reason for the audit log', { exact: true }).fill('Attempt after permission removal');
      await dialog.getByRole('button', { name: 'Save decision', exact: true }).click();
    }
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: member.nickname, exact: true })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Dearly management', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Verify age', exact: true })).toHaveCount(0);
  });
}

test('restoring a management page from browser history rechecks the session', async ({ page }) => {
  const control = await fixture(page);
  await enterManagement(page);
  await page.getByRole('button', { name: 'Accounts', exact: true }).click();
  await expect(page.getByRole('heading', { name: member.nickname, exact: true })).toBeVisible();
  const reads = control.accessReads;
  control.accessStatus = 403; control.stateStatus = 503;
  await page.evaluate(() => dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })));
  await expect.poll(() => control.accessReads).toBeGreaterThan(reads);
  await expect(page.getByRole('heading', { name: member.nickname, exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Dearly management', exact: true })).toHaveCount(0);
});

test('real management documents and APIs reject guests and ordinary browser accounts', async ({ page, context }) => {
  for (const path of ['/management', '/management/', '/management/accounts', '/v1/staff/access', '/v1/staff/users', '/v1/staff/reports', '/v1/staff/audit']) {
    expect((await context.request.get(path)).status(), path).toBe(401);
  }
  const signup = await context.request.post('/v1/auth/register', { headers: { 'X-Dearly-Client': 'web' },
    data: { username: `member_guard_${Date.now()}`, password: 'management-test-password', nickname: 'Regular member', birthDate: '2000-01-01' } });
  expect(signup.status()).toBe(201);
  const user = await signup.json();
  for (const path of ['/management', '/management/', '/management/accounts', '/v1/staff/access', '/v1/staff/users', '/v1/staff/reports', '/v1/staff/audit']) {
    expect((await context.request.get(path)).status(), path).toBe(403);
  }
  await page.addInitScript(id => localStorage.setItem(`dearly.guide.v1:${id}`, 'seen'), user.userID);
  await page.goto('/settings');
  await expect(page.getByRole('heading', { name: 'Your space, your pace.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Management', exact: true })).toHaveCount(0);
});
