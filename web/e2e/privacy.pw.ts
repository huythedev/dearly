import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import fixture from '../src/fixtures/encryption-v1.json' with { type: 'json' };

test('another device winning key initialization opens recovery without replacing its keys', async ({ page }) => {
  const userID = fixture.alice.bundle.userID;
  await page.addInitScript(id => localStorage.setItem(`dearly.guide.v1:${id}`, 'seen'), userID);
  await page.routeWebSocket('**/ws/chat', () => {});
  let initializedElsewhere = false, publishes = 0;
  await page.route('**/v1/**', route => {
    const url = route.request().url();
    if (url.endsWith('/state')) return route.fulfill({ json: { serverNow: 813585600, state: {
      currentUserID: userID, profiles: [{ id: userID, nickname: 'Recovery friend', age: 25, ageVerified: true,
        symbol: 'leaf.fill', bio: '', interests: [], support: 'listen', pace: 'Evenings' }],
      messages: [], connections: [], comments: [], invitations: [], suggestedUserIDs: [],
      journals: [{ id: fixture.journalID, authorID: userID, title: '', body: fixture.journal, sharedText: '', audience: 'privateOnly',
        connectionID: null, anonymous: false, commentsEnabled: true, support: 'listen', date: 813585600, listeners: [], canInviteAuthor: false, moderationHidden: false }],
    } } });
    if (url.endsWith('/encryption/identity')) {
      if (route.request().method() === 'POST') {
        publishes++; initializedElsewhere = true;
        expect(route.request().postDataJSON().agreementKey).not.toBe(fixture.alice.bundle.agreementKey);
        return route.fulfill({ status: 409, json: { detail: 'Another device initialized first' } });
      }
      return initializedElsewhere ? route.fulfill({ json: fixture.alice.bundle }) : route.fulfill({ status: 404, json: { detail: 'Not initialized' } });
    }
    return route.fulfill({ json: { items: [], nextCursor: null } });
  });
  await page.goto('/journal');
  await expect(page.getByRole('heading', { name: 'Locked entry', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Encryption settings', exact: true }).click();
  await page.getByRole('textbox', { name: 'Recovery code', exact: true }).fill(fixture.alice.recoveryCode);
  await page.getByRole('button', { name: 'Unlock encryption', exact: true }).click();
  await expect(page.getByText('Encryption ready', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: /My journal/ }).click();
  await expect(page.getByRole('heading', { name: fixture.journalContent.title, exact: true })).toBeVisible();
  expect(publishes).toBe(1);
});

test('simultaneous first logins share one persisted encryption identity across tabs', async ({ page, context }) => {
  await page.goto('/');
  const signup = await context.request.post('/v1/auth/register', { headers: { 'X-Dearly-Client': 'web' },
    data: { username: `keyrace_${Date.now()}`, password: 'privacy-test-password', nickname: 'Two tabs', birthDate: '2000-01-01' } });
  expect(signup.status()).toBe(201);
  const user = await signup.json();
  await context.addInitScript(id => localStorage.setItem(`dearly.guide.v1:${id}`, 'seen'), user.userID);
  let reads = 0, writes = 0;
  let releaseReads!: () => void, releaseWrites!: () => void;
  const reading = new Promise<void>(resolve => { releaseReads = resolve; });
  const writing = new Promise<void>(resolve => { releaseWrites = resolve; });
  const published: unknown[] = [];
  await context.route('**/v1/encryption/identity', async route => {
    if (route.request().method() === 'GET') {
      const response = await route.fetch();
      if (++reads <= 2) { if (reads === 2) releaseReads(); await reading; }
      return route.fulfill({ response });
    }
    published.push(route.request().postDataJSON());
    if (++writes === 2) releaseWrites();
    await writing;
    return route.continue();
  });
  try {
    const second = await context.newPage();
    await Promise.all([page.goto('/journal'), second.goto('/journal')]);
    for (const tab of [page, second]) await expect(tab.getByRole('button', { name: 'Encryption settings', exact: true })).toBeVisible();
    expect(published).toHaveLength(2); expect(published[0]).toEqual(published[1]);
    const codes = [];
    for (const tab of [page, second]) {
      await tab.getByRole('button', { name: 'Encryption settings', exact: true }).click();
      await tab.getByRole('button', { name: 'Show recovery code', exact: true }).click();
      codes.push(await tab.getByRole('textbox', { name: 'Recovery code', exact: true }).inputValue());
      await tab.reload();
      await expect(tab.getByText('Encryption ready', { exact: true })).toBeVisible();
    }
    expect(codes[0]).toBe(codes[1]);
    await second.close();
  } finally { releaseReads(); releaseWrites(); }
});

test('private ciphertext, recovery on another device, data download and permanent deletion', async ({ page, context, browser }) => {
  const username = `privacy_${Date.now()}`, password = 'privacy-test-password';
  await page.goto('/');
  const signup = await context.request.post('/v1/auth/register', { headers: { 'X-Dearly-Client': 'web' },
    data: { username, password, nickname: 'Privacy friend', birthDate: '2000-01-01' } });
  expect(signup.status()).toBe(201);
  const user = await signup.json();
  await page.addInitScript(id => localStorage.setItem(`dearly.guide.v1:${id}`, 'seen'), user.userID);
  await page.goto('/journal');
  await page.getByRole('button', { name: 'Encryption settings', exact: true }).click();
  await page.getByRole('button', { name: 'Show recovery code', exact: true }).click();
  const recoveryCode = await page.getByRole('textbox', { name: 'Recovery code', exact: true }).inputValue();
  expect(recoveryCode).toMatch(/^DEARLY1-[A-Za-z0-9_-]{43}$/);
  await page.getByRole('button', { name: 'I saved my recovery code', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Encryption settings', exact: true })).toHaveCount(0);
  await page.getByRole('link', { name: /My journal/ }).click();
  await page.getByRole('button', { name: 'New entry', exact: true }).click();
  const dialog = page.getByRole('dialog');
  const body = `Chỉ mình đọc được 🌱 ${Date.now()}`;
  await dialog.getByLabel('Title', { exact: true }).fill('My encrypted title');
  await dialog.getByLabel('Your words', { exact: true }).fill(body);
  await dialog.getByRole('button', { name: 'Save privately', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  const rawState = await (await context.request.get('/v1/state')).json();
  const rawJournal = rawState.state.journals[0];
  expect(rawJournal.body).toMatch(/^dearly:e2ee:1:/); expect(rawJournal.title).toBe('');
  expect(JSON.stringify(rawState)).not.toContain(body); expect(JSON.stringify(rawState)).not.toContain('My encrypted title');
  await page.reload();
  await expect(page.getByRole('heading', { name: 'My encrypted title', exact: true })).toBeVisible();

  const second = await browser.newContext({ baseURL: new URL(page.url()).origin, viewport: page.viewportSize()! });
  try {
    await second.addCookies(await context.cookies());
    await second.addInitScript(id => localStorage.setItem(`dearly.guide.v1:${id}`, 'seen'), user.userID);
    const device = await second.newPage();
    await device.goto('/journal');
    await expect(device.getByRole('heading', { name: 'Locked entry', exact: true })).toBeVisible();
    await device.getByRole('button', { name: 'Encryption settings', exact: true }).click();
    await device.getByRole('textbox', { name: 'Recovery code', exact: true }).fill('DEARLY1-' + 'A'.repeat(43));
    await device.getByRole('button', { name: 'Unlock encryption', exact: true }).click();
    await expect(device.getByRole('alert')).toContainText('The recovery code does not match this account.');
    await device.getByRole('textbox', { name: 'Recovery code', exact: true }).fill(recoveryCode);
    await device.getByRole('button', { name: 'Unlock encryption', exact: true }).click();
    await expect(device.getByText('Encryption ready', { exact: true })).toBeVisible();
    await device.getByRole('link', { name: /My journal/ }).click();
    await expect(device.getByRole('heading', { name: 'My encrypted title', exact: true })).toBeVisible();
    await expect(device.locator('.journal-card')).toContainText(body);
    await device.getByRole('button', { name: 'Account settings', exact: true }).click();
    await device.getByRole('button', { name: 'Download my data', exact: true }).click();
    const exportDialog = device.getByRole('dialog', { name: 'Download your data', exact: true });
    await exportDialog.getByLabel('Current password', { exact: true }).fill(password);
    const downloading = device.waitForEvent('download');
    await exportDialog.getByRole('button', { name: 'Download data', exact: true }).click();
    const download = await downloading;
    const exported = JSON.parse(await readFile((await download.path())!, 'utf8'));
    expect(exported.profile.username).toBe(username);
    expect(exported.journals[0].body).toBe(body);
    expect(exported.encryptedOriginal.journals[0].body).toMatch(/^dearly:e2ee:1:/);
    expect(JSON.stringify(exported)).not.toContain(password);
    await device.getByRole('button', { name: 'Delete my account', exact: true }).click();
    const deletion = device.getByRole('dialog', { name: 'Permanently delete your account?', exact: true });
    await deletion.getByLabel('Current password', { exact: true }).fill(password);
    await deletion.getByLabel('Type DELETE to confirm', { exact: true }).fill('DELETE');
    await deletion.getByRole('button', { name: 'Permanently delete', exact: true }).click();
    await expect(device.getByRole('heading', { name: 'Welcome back.', exact: true })).toBeVisible();
    const remainingKeys = await device.evaluate(() => new Promise<number>((resolve, reject) => {
      const opening = indexedDB.open('dearly-encryption', 1);
      opening.onsuccess = () => {
        const db = opening.result;
        const request = db.transaction('keys').objectStore('keys').count();
        request.onsuccess = () => { resolve(request.result); db.close(); };
        request.onerror = () => reject(request.error);
      };
      opening.onerror = () => reject(opening.error);
    }));
    expect(remainingKeys).toBe(0);
    expect((await context.request.get('/v1/state')).status()).toBe(401);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Welcome back.', exact: true })).toBeVisible();
  } finally { await second.close(); }
});
