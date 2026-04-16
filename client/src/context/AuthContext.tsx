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

interface AuthMeResponse {
  success?: boolean;
  data?: {
    require_auth?: boolean;
    authenticated?: boolean;
    user?: AuthUser | null;
    permissions?: string[];
  };
}

interface AuthContextValue {
  user: AuthUser | null;
  permissions: string[];
  isLoading: boolean;
  isLoggedIn: boolean;
  requireAuth: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  permissions: [],
  isLoading: true,
  isLoggedIn: false,
  requireAuth: false,
  refresh: async () => {},
  logout: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [requireAuth, setRequireAuth] = useState(false);
  const [, navigate] = useLocation();

  const refresh = useCallback(async () => {
    try {
      const result = await apiGet<AuthMeResponse>("/api/auth/me");
      const auth = result.data;
      setUser(auth?.user || null);
      setPermissions(auth?.permissions || []);
      setRequireAuth(!!auth?.require_auth);
    } catch (reason: unknown) {
      setUser(null);
      setPermissions([]);
      setRequireAuth(reason instanceof ApiError && reason.status === 401);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiPost("/api/auth/logout");
    } catch {}
    setUser(null);
    setPermissions([]);
    setRequireAuth(false);
    await refresh();
    navigate("/");
  }, [navigate, refresh]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <AuthContext.Provider value={{ user, permissions, isLoading, isLoggedIn: !!user, requireAuth, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
