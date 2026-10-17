const moderator = ['reports.read', 'reports.review', 'reports.hide', 'users.read', 'users.verify_age'];
const admin = [...moderator, 'roles.manage', 'users.suspend', 'audit.read'];

export interface StaffClaims { currentUserRole?: string; permissions?: unknown }

export function hasStaffPermission(claims: StaffClaims | null | undefined, permission: string): boolean {
  const allowed = claims?.currentUserRole === 'admin' ? admin : claims?.currentUserRole === 'moderator' ? moderator : [];
  return allowed.includes(permission) && Array.isArray(claims?.permissions) && claims.permissions.includes(permission);
}

export function staffScope(claims: StaffClaims | null | undefined): string {
  return `${claims?.currentUserRole ?? ''}:${admin.filter(permission => hasStaffPermission(claims, permission)).sort().join(',')}`;
}
