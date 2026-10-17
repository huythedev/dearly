import { expect, it } from 'vitest';
import { hasStaffPermission } from './permissions';

it('denies stale permission lists for members, missing roles and unknown roles', () => {
  for (const currentUserRole of ['user', undefined, 'owner', 'ADMIN']) {
    expect(hasStaffPermission({ currentUserRole, permissions: ['reports.read', 'roles.manage'] }, 'reports.read')).toBe(false);
  }
  expect(hasStaffPermission({ currentUserRole: 'admin', permissions: 'reports.read' }, 'reports.read')).toBe(false);
  expect(hasStaffPermission({ currentUserRole: 'admin' }, 'reports.read')).toBe(false);
});

it('requires both a staff role and its explicit permission, with moderator limits', () => {
  expect(hasStaffPermission({ currentUserRole: 'admin', permissions: [] }, 'reports.read')).toBe(false);
  expect(hasStaffPermission({ currentUserRole: 'admin', permissions: ['roles.manage'] }, 'roles.manage')).toBe(true);
  expect(hasStaffPermission({ currentUserRole: 'moderator', permissions: ['users.verify_age'] }, 'users.verify_age')).toBe(true);
  for (const permission of ['roles.manage', 'users.suspend', 'audit.read', 'unknown']) {
    expect(hasStaffPermission({ currentUserRole: 'moderator', permissions: [permission] }, permission)).toBe(false);
  }
});
