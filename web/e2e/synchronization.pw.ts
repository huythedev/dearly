import { expect, test } from '@playwright/test';
import type { Envelope, Journal } from '../src/types';

const userID = '11111111-1111-4111-8111-111111111111';
const envelope: Envelope = {
  serverNow: 813585600,
  state: {
    currentUserID: userID, profiles: [{ id: userID, nickname: 'Test friend', age: 25, ageVerified: true,
      symbol: 'leaf.fill', bio: '', interests: [], support: 'listen', pace: 'Evenings' }],
    journals: [], messages: [], connections: [], comments: [], invitations: [], suggestedUserIDs: [],
  },
};
const entry = (title: string): Journal => ({
  id: title, authorID: userID, title, body: 'Synthetic test entry', sharedText: '', audience: 'privateOnly',
  connectionID: null, anonymous: true, commentsEnabled: true, support: 'listen', date: 813585600,
  listeners: [], canInviteAuthor: false, moderationHidden: false,
});

test('a socket invalidation during a snapshot triggers a fresh serialized read', async ({ page }) => {
  let reads = 0;
  let active = 0;
  let peak = 0;
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let changed!: () => void;
  await page.routeWebSocket('**/ws/chat', socket => {
    changed = () => socket.send(JSON.stringify({ type: 'state.changed' }));
    socket.onMessage(() => socket.send(JSON.stringify({ type: 'ready' })));
  });
  await page.route('**/v1/journals?*', route => route.fulfill({ json: { items: [], nextCursor: null } }));
  await page.route('**/v1/state', async route => {
    const read = ++reads;
    active++; peak = Math.max(peak, active);
    if (read === 2) await held;
    await route.fulfill({ json: read >= 3 ? { ...envelope, state: { ...envelope.state, journals: [entry('Latest snapshot')] } } : envelope });
    active--;
  });
  try {
    await page.goto('/journal');
    await expect.poll(() => reads).toBe(2);
    changed(); changed();
    release();
    await expect(page.getByRole('heading', { name: 'Latest snapshot', exact: true })).toBeVisible();
    expect(reads).toBe(3);
    expect(peak).toBe(1);
  } finally { release(); }
});

test('same-frame pagination clicks issue only one request', async ({ page }) => {
  let reads = 0;
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.routeWebSocket('**/ws/chat', () => {});
  await page.route('**/v1/state', route => route.fulfill({ json: envelope }));
  await page.route('**/v1/journals?*', async route => {
    const read = ++reads;
    if (read > 1) await held;
    await route.fulfill({ json: { items: [entry(read === 1 ? 'First page' : 'Older page')], nextCursor: read === 1 ? 'cursor' : null } });
  });
  try {
    await page.goto('/journal');
    const more = page.getByRole('button', { name: 'Older entries', exact: true });
    await expect(more).toBeVisible();
    await more.evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
    await expect.poll(() => reads).toBe(2);
    release();
    await expect(page.getByRole('heading', { name: 'Older page', exact: true })).toBeVisible();
    expect(reads).toBe(2);
  } finally { release(); }
});

test('system appearance controls and signup date fields stay in sync', async ({ page }) => {
  await page.route('**/v1/state', route => route.fulfill({ status: 401, json: { detail: 'Please log in.' } }));
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Dark appearance', exact: true })).toBeVisible();
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.getByRole('button', { name: 'Light appearance', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  for (const width of [320, 390, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    for (const locale of ['en', 'vi']) {
      await page.locator('.preference-controls select').selectOption(locale);
      for (const date of ['', '2000-01-01']) {
        await page.locator('input[name="birthDate"]').fill(date);
        const sizes = await page.locator('.auth-card form').evaluate(form => {
          const dob = form.querySelector('input[name="birthDate"]')!.getBoundingClientRect();
          const username = form.querySelector('input[name="username"]')!.getBoundingClientRect();
          return { dob: dob.width, username: username.width, overflow: document.documentElement.scrollWidth > innerWidth };
        });
        expect(Math.abs(sizes.dob - sizes.username)).toBeLessThan(1);
        expect(sizes.overflow).toBe(false);
      }
    }
  }
});
