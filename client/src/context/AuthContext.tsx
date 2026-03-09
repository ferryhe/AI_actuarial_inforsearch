import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useLocation } from "wouter";
import { apiGet, apiPost, ApiError } from "@/lib/api";

export interface AuthUser {
  id: number | null;
  email: string | null;
  display_name: string;
  role: string;
  is_active: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  isLoggedIn: boolean;
  requireAuth: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  isLoading: true,
  isLoggedIn: false,
  requireAuth: false,
  refresh: async () => {},
  logout: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [requireAuth, setRequireAuth] = useState(false);
  const [, navigate] = useLocation();

  const refresh = useCallback(async () => {
    try {
      // Fetch require_auth flag alongside user identity
      const [meRes, authRes] = await Promise.allSettled([
        apiGet<{ success: boolean; user: AuthUser }>("/api/user/me"),
        apiGet<{ require_auth: boolean }>("/api/auth/me"),
      ]);
      setUser(meRes.status === "fulfilled" ? (meRes.value.user ?? null) : null);
      // Derive requireAuth:
      // - if /api/auth/me succeeds, use its require_auth flag
      // - if it fails with status 401, the backend has auth enabled but the user
      //   is unauthenticated — treat that as requireAuth=true so the guard activates
      // - otherwise, default to false (open access) when the endpoint is unavailable
      let requireAuthFlag = false;
      if (authRes.status === "fulfilled") {
        requireAuthFlag = Boolean(authRes.value.require_auth);
      } else {
        const reason: unknown = authRes.reason;
        if (reason instanceof ApiError && reason.status === 401) {
          requireAuthFlag = true;
        }
      }
      setRequireAuth(requireAuthFlag);
    } catch {
      setUser(null);
      setRequireAuth(false);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiPost("/logout");
    } catch {
      // ignore errors – clear local state regardless
    }
    setUser(null);
    navigate("/login");
  }, [navigate]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <AuthContext.Provider value={{ user, isLoading, isLoggedIn: !!user, requireAuth, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
