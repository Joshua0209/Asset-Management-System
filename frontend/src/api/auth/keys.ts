// Endpoint paths for the auth domain.
// Centralized so callers don't pass raw strings around.

export const AUTH_PATHS = {
  login: "/auth/login",
  register: "/auth/register",
  me: "/auth/me",
  // Manager-only "create user of any role" — see 12-api-design.md §1.6.
  // Not yet wired from the FE; reserved for the future user-management page.
  users: "/auth/users",
} as const;
