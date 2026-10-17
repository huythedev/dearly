import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

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
