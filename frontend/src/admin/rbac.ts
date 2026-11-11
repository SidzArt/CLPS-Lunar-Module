/** Client-side RBAC UX helpers mirroring backend RequireRole checks. */

export function hasAnyRole(userRoles: readonly string[] | undefined, ...allowed: string[]): boolean {
  if (!userRoles || userRoles.length === 0) {
    return false;
  }
  if (userRoles.includes("super_admin")) {
    return true;
  }
  if (allowed.length === 0) {
    return true;
  }
  return allowed.some((role) => userRoles.includes(role));
}

export function isSuperAdmin(userRoles: readonly string[] | undefined): boolean {
  return Boolean(userRoles?.includes("super_admin"));
}

