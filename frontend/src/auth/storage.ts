import type { AuthSession } from "../api/auth";

const STORAGE_KEY = "ams-auth";

export function loadSession(): AuthSession | null {
  try {
    const raw = globalThis.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AuthSession>;
    if (!parsed.token || !parsed.expiresAt || !parsed.user) return null;
    if (new Date(parsed.expiresAt).getTime() <= Date.now()) {
      globalThis.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return parsed as AuthSession;
  } catch {
    return null;
  }
}

export function saveSession(session: AuthSession): void {
  globalThis.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  globalThis.localStorage.removeItem(STORAGE_KEY);
}

export function getToken(): string | null {
  return loadSession()?.token ?? null;
}

export const UNAUTHORIZED_EVENT = "ams:auth-unauthorized";
