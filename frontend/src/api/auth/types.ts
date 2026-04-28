// Types shared by the auth API client and the auth state context.
// Mirrors docs/system-design/12-api-design.md §1.

export type UserRole = "holder" | "manager";

/** Subset of the backend `UserRead` we actually consume in the FE. */
export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: UserRole;
}

/** Full session payload persisted to localStorage after a successful login. */
export interface AuthSession {
  token: string;
  expiresAt: string;
  user: AuthUser;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  name: string;
  department: string;
}
