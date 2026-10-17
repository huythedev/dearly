import { expect, test } from '@playwright/test';
import type { Command, Envelope, StaffUser } from '../src/types';

for (const role of ['moderator', 'admin'] as const) {
  test(`${role} can review age with only the permitted account controls`, async ({ page }) => {
    const userID = '44444444-4444-4444-8444-444444444444';
    const member: StaffUser = { id: '55555555-5555-4555-8555-555555555555', username: 'member', nickname: 'Member friend',
      role: 'user', suspended: false, ageVerified: false, birthDate: '2000-01-01' };
    const permissions = ['reports.read', 'reports.review', 'reports.hide', 'users.read', 'users.verify_age',
      ...(role === 'admin' ? ['roles.manage', 'users.suspend', 'audit.read'] : [])];
    const envelope: Envelope = { serverNow: 813585600, state: {
      currentUserID: userID, currentUserRole: role, permissions,
      profiles: [{ id: userID, nickname: 'Age reviewer', age: 25, ageVerified: true,
        symbol: 'leaf.fill', bio: '', interests: [], support: 'listen', pace: 'Evenings' }],
      journals: [], messages: [], connections: [], comments: [], invitations: [], suggestedUserIDs: [],
    } };
    const actions: Command[] = [];
    await page.addInitScript(id => localStorage.setItem(`dearly.guide.v1:${id}`, 'seen'), userID);
    await page.routeWebSocket('**/ws/chat', socket => socket.onMessage(() => socket.send(JSON.stringify({ type: 'ready' }))));
    await page.route('**/v1/**', route => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith('/state')) return route.fulfill({ json: envelope });
      if (url.pathname.endsWith('/staff/access')) return route.fulfill({ json: { userID, currentUserRole: role, permissions } });
      if (url.pathname.endsWith('/staff/users')) return route.fulfill({ json: { items: [member], nextCursor: null } });
      if (url.pathname.endsWith('/actions')) {
        const command: Command = route.request().postDataJSON();
        actions.push(command);
        if (command.kind === 'staff.user.verify_age') member.ageVerified = true;
        return route.fulfill({ json: { ok: true } });
      }
      return route.fulfill({ json: { items: [], nextCursor: null } });
    });
    await page.goto('/settings');
    await page.locator('.account-actions').getByRole('button', { name: 'Management', exact: true }).click();
    await page.getByRole('button', { name: 'Accounts', exact: true }).click();
    await expect(page.getByRole('heading', { name: member.nickname, exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Change role', exact: true })).toHaveCount(role === 'admin' ? 1 : 0);
    await expect(page.getByRole('button', { name: 'Suspend account', exact: true })).toHaveCount(role === 'admin' ? 1 : 0);
    await expect(page.getByRole('button', { name: 'Audit log', exact: true })).toHaveCount(role === 'admin' ? 1 : 0);
    await page.getByRole('button', { name: 'Verify age', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Verify age', exact: true });
    await expect(dialog.getByLabel('Reviewed date of birth', { exact: true })).toHaveValue(member.birthDate);
    await dialog.getByRole('button', { name: 'Save decision', exact: true }).click();
    expect(actions).toHaveLength(0); // A reason is required before submitting a review.
    await dialog.getByLabel('Reason for the audit log', { exact: true }).fill('Birth date reviewed with the member');
    await dialog.getByRole('button', { name: 'Save decision', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(actions).toHaveLength(1);
    expect(actions[0]).toMatchObject({ kind: 'staff.user.verify_age', payload: {
      userID: member.id, birthDate: '2000-01-01', reason: 'Birth date reviewed with the member',
    } });
    await expect(page.locator('.account-card')).toContainText('Verified');
  });
}
