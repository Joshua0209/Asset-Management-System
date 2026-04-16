import { useAuthStore } from '@/stores/authStore';

/**
 * Convenience hook for auth state and actions.
 * Components use this instead of importing the store directly.
 */
export function useAuth() {
  const { user, token, isAuthenticated, setAuth, logout } = useAuthStore();

  return {
    user,
    token,
    isAuthenticated,
    role: user?.role ?? null,
    isManager: user?.role === 'manager',
    isHolder: user?.role === 'holder',
    setAuth,
    logout,
  };
}
