import { expect, test, type Page } from '@playwright/test';
import { guideSteps, guideStorageKey } from '../src/guide/model';
import type { Envelope } from '../src/types';

const userID = '22222222-2222-4222-8222-222222222222';
async function fixture(page: Page, connected = false) {
  const envelope: Envelope = {
    serverNow: 813585600,
    state: {
      currentUserID: userID, profiles: [{ id: userID, nickname: 'Guide friend', age: 25, ageVerified: true,
        symbol: 'leaf.fill', bio: '', interests: [], support: 'listen', pace: 'Evenings' }],
      journals: [], messages: [], comments: [], invitations: [], suggestedUserIDs: [],
      connections: connected ? [{ id: 'garden', members: [userID, 'friend'], startedAt: 813585600,
        endedAt: null, paused: false, checkIns: {}, bestStreak: 0, serverTotalDays: 0, serverCurrentStreak: 0 }] : [],
    },
  };
  const writes: string[] = [];
  await page.routeWebSocket('**/ws/chat', socket => {
    socket.onMessage(() => socket.send(JSON.stringify({ type: 'ready' })));
  });
  await page.route('**/v1/**', route => {
    if (route.request().method() !== 'GET') writes.push(route.request().url());
    return route.fulfill({ json: route.request().url().endsWith('/state') ? envelope : { items: [], profiles: [], nextCursor: null } });
  });
  return writes;
}

async function alignedSpotlight(page: Page, target: string) {
  await expect(page.locator('[data-guide-hole]')).toBeVisible();
  await expect.poll(async () => page.evaluate(name => {
    const control = document.querySelector(`[data-guide="${name}"]`)!.getBoundingClientRect();
    const hole = document.querySelector('[data-guide-hole]')!.getBoundingClientRect();
    return hole.left <= control.left + 1 && hole.right >= control.right - 1
      && hole.top <= control.top + 1 && hole.bottom >= control.bottom - 1;
  }, target)).toBe(true);
  const screen = page.viewportSize()!;
  await expect.poll(async () => {
    const card = await page.locator('.guide-card').boundingBox();
    return !!card && card.x >= 15 && card.y >= 15 && card.x + card.width <= screen.width - 15
      && card.y + card.height <= screen.height - 15;
  }).toBe(true);
  await expect.poll(async () => page.evaluate(() => {
    const card = document.querySelector('.guide-card')!.getBoundingClientRect();
    const hole = document.querySelector('[data-guide-hole]')!.getBoundingClientRect();
    return Math.max(0, Math.min(card.right, hole.right) - Math.max(card.left, hole.left))
      * Math.max(0, Math.min(card.bottom, hole.bottom) - Math.max(card.top, hole.top));
  })).toBeLessThan(1);
}

test('welcome can be deferred, remembered and replayed from settings', async ({ page }) => {
  await fixture(page);
  await page.goto('/journal');
  await expect(page.getByRole('dialog', { name: 'A little guide to Dearly' })).toBeVisible();
  await page.getByRole('button', { name: 'Maybe later', exact: true }).click();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Make room for your thoughts.' })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: 'Account settings', exact: true }).click();
  await page.getByRole('button', { name: 'Take a guided tour', exact: true }).click();
  await expect(page.getByRole('dialog', { name: guideSteps[0].title })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Account settings', exact: true })).toBeFocused();
  expect(await page.evaluate(key => localStorage.getItem(key), guideStorageKey(userID))).toBe('seen');
});

test('first-login welcome follows the visible viewport through keyboard resize and panning', async ({ page }) => {
  await fixture(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    // Model the smaller, panned viewport while the mobile login keyboard closes.
    const viewport = Object.assign(new EventTarget(), { width: 390, height: 300, offsetLeft: 0, offsetTop: 180, scale: 1 });
    Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true });
    Object.assign(window, { updateGuideViewport(values: object, event: string) {
      Object.assign(viewport, values); viewport.dispatchEvent(new Event(event));
    } });
  });
  let authenticated = false;
  await page.route('**/v1/state', route => authenticated ? route.fallback() : route.fulfill({ status: 401, json: { detail: 'Sign in' } }));
  await page.route('**/v1/auth/login', route => {
    authenticated = true;
    return route.fulfill({ json: { userID, expiresAt: 816177600 } });
  });
  await page.goto('/journal');
  await page.getByLabel('Username', { exact: true }).fill('guide_friend');
  await page.getByLabel('Password', { exact: true }).fill('guide-test-password');
  await page.getByRole('button', { name: 'Come on in', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'A little guide to Dearly' })).toBeVisible();
  const fitsVisibleViewport = () => page.evaluate(() => {
    const card = document.querySelector('.guide-card')!.getBoundingClientRect();
    const viewport = window.visualViewport!;
    return card.left >= viewport.offsetLeft + 15 && card.right <= viewport.offsetLeft + viewport.width - 15
      && card.top >= viewport.offsetTop + 15 && card.bottom <= viewport.offsetTop + viewport.height - 15;
  });
  await expect.poll(fitsVisibleViewport).toBe(true);
  await page.evaluate(() => (window as unknown as { updateGuideViewport: (values: object, event: string) => void })
    .updateGuideViewport({ offsetTop: 60 }, 'scroll'));
  await expect.poll(fitsVisibleViewport).toBe(true);
  await page.evaluate(() => (window as unknown as { updateGuideViewport: (values: object, event: string) => void })
    .updateGuideViewport({ offsetTop: 0, height: 844 }, 'resize'));
  await expect.poll(fitsVisibleViewport).toBe(true);
  await page.getByRole('button', { name: 'Show me around', exact: true }).click();
  await alignedSpotlight(page, guideSteps[0].target);
  await page.getByRole('button', { name: 'Skip guide', exact: true }).click();
  await page.getByRole('button', { name: 'Account settings', exact: true }).click();
  await page.getByRole('button', { name: 'Take a guided tour', exact: true }).click();
  await alignedSpotlight(page, guideSteps[0].target);
});

test('six steps highlight real controls without writing data and keep keyboard focus inside', async ({ page }) => {
  const writes = await fixture(page, true);
  await page.goto('/journal');
  await page.getByRole('button', { name: 'Show me around', exact: true }).click();
  for (let i = 0; i < guideSteps.length; i++) {
    const step = guideSteps[i];
    const dialog = page.getByRole('dialog', { name: step.title });
    await expect(dialog).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/${step.route}$`));
    await alignedSpotlight(page, step.target);
    for (let tab = 0; tab < 5; tab++) {
      await page.keyboard.press('Tab');
      expect(await page.evaluate(() => !!document.activeElement?.closest('dialog[open]'))).toBe(true);
    }
    if (i === 1) {
      await dialog.getByRole('button', { name: 'Back', exact: true }).click();
      await expect(page.getByRole('dialog', { name: guideSteps[0].title })).toBeVisible();
      await page.getByRole('button', { name: 'Next', exact: true }).click();
    }
    await dialog.getByRole('button', { name: i === guideSteps.length - 1 ? 'Finish' : 'Next', exact: true }).click();
  }
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(writes).toEqual([]);
  expect(await page.evaluate(key => localStorage.getItem(key), guideStorageKey(userID))).toBe('seen');
  await page.reload();
  await expect(page.getByRole('heading', { name: 'A little care goes a long way.', exact: true })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('long instructions reset between steps and can be read with the keyboard', async ({ page }) => {
  await fixture(page);
  await page.setViewportSize({ width: 320, height: 320 });
  await page.addInitScript(() => localStorage.setItem('dearly.language', 'vi'));
  await page.goto('/journal');
  await page.getByRole('button', { name: 'Bắt đầu khám phá', exact: true }).click();
  const copy = page.locator('.guide-copy');
  await expect.poll(() => copy.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true);
  await page.keyboard.press('Tab');
  await page.keyboard.press('Tab');
  await expect(copy).toBeFocused();
  await page.keyboard.press('PageDown');
  await expect.poll(() => copy.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
  await page.keyboard.press('Shift+Tab');
  await expect(page.getByRole('button', { name: 'Bỏ qua hướng dẫn', exact: true })).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(page.getByRole('button', { name: 'Tiếp', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog', { name: 'Tìm lại những trang viết' })).toBeVisible();
  // Layout/scroll anchoring can round by a pixel; the previous offset hid part of the title.
  await expect.poll(() => copy.evaluate(element => element.scrollTop)).toBeLessThanOrEqual(1);
  await page.keyboard.press('Tab');
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Shift+Tab');
  await expect(page.getByRole('button', { name: 'Quay lại', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog', { name: 'Một trang dành riêng cho bạn' })).toBeVisible();
  await expect.poll(() => copy.evaluate(element => element.scrollTop)).toBeLessThanOrEqual(1);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

for (const connected of [false, true]) {
  test(`Vietnamese instructions fit rotation and missing targets (connected: ${connected})`, async ({ page }) => {
    await fixture(page, connected);
    await page.addInitScript(() => { localStorage.setItem('dearly.language', 'vi'); localStorage.setItem('dearly.appearance', 'dark'); });
    await page.setViewportSize({ width: 320, height: 568 });
    await page.goto('/garden');
    await expect(page.getByRole('dialog', { name: 'Cùng làm quen với Dearly' })).toBeVisible();
    await page.getByRole('button', { name: 'Bắt đầu khám phá', exact: true }).click();
    for (let i = 0; i < guideSteps.length; i++) {
      await expect(page.locator('.guide-topline')).toContainText(`Bước ${i + 1} trên 6`);
      await alignedSpotlight(page, guideSteps[i].target);
      if (i === 0) {
        await page.setViewportSize({ width: 568, height: 320 });
        await alignedSpotlight(page, 'compose');
        await page.evaluate(() => {
          document.querySelector('[data-guide="compose"]')!.removeAttribute('data-guide');
          dispatchEvent(new Event('resize'));
        });
        await expect(page.locator('[data-guide-hole]')).toHaveCount(0);
        await expect(page.getByRole('button', { name: 'Tiếp', exact: true })).toBeVisible();
        await page.setViewportSize({ width: 320, height: 568 });
      }
      if (i > 0) {
        await page.setViewportSize({ width: 568, height: 320 });
        await alignedSpotlight(page, guideSteps[i].target);
        await page.setViewportSize({ width: 320, height: 568 });
        await alignedSpotlight(page, guideSteps[i].target);
      }
      await page.getByRole('button', { name: i === guideSteps.length - 1 ? 'Hoàn tất' : 'Tiếp', exact: true }).click();
    }
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });
}
