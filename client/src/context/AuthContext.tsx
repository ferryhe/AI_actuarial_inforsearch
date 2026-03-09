import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useLocation } from "wouter";
import { apiGet, apiPost } from "@/lib/api";

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
      // Default to false (open access) when the endpoint is unavailable
      setRequireAuth(authRes.status === "fulfilled" ? Boolean(authRes.value.require_auth) : false);
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
