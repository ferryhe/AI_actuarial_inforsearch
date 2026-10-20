import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useLocation } from "wouter";
import { apiGet, apiPost, ApiError, setStoredAuthToken } from "@/lib/api";

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
    require_auth: boolean;
    authenticated: boolean;
    user: AuthUser | null;
    permissions: string[];
    read_only?: boolean;
  };
}

interface AuthContextValue {
  user: AuthUser | null;
  permissions: string[];
  isLoading: boolean;
  authError: boolean;
  isLoggedIn: boolean;
  requireAuth: boolean;
  isReadOnlyHub: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  permissions: [],
  isLoading: true,
  authError: false,
  isLoggedIn: false,
  requireAuth: false,
  isReadOnlyHub: false,
  refresh: async () => {},
  logout: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState(false);
  const [requireAuth, setRequireAuth] = useState(false);
  const [isReadOnlyHub, setIsReadOnlyHub] = useState(false);
  const [, navigate] = useLocation();

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setAuthError(false);
    try {
      const result = await apiGet<AuthMeResponse>("/api/auth/me");
      const auth = result?.data;
      if (
        !auth ||
        typeof auth !== "object" ||
        typeof auth.require_auth !== "boolean" ||
        typeof auth.authenticated !== "boolean" ||
        !("user" in auth) ||
        (auth.user !== null && (typeof auth.user !== "object" || Array.isArray(auth.user))) ||
        !Array.isArray(auth.permissions) ||
        !auth.permissions.every((permission) => typeof permission === "string") ||
        (auth.read_only !== undefined && typeof auth.read_only !== "boolean")
      ) {
        throw new Error("Invalid auth metadata");
      }
      setUser(auth.user);
      setPermissions(auth.permissions);
      setRequireAuth(auth.require_auth);
      setIsReadOnlyHub(auth.read_only === true);
    } catch (reason: unknown) {
      setUser(null);
      setPermissions([]);
      setRequireAuth(reason instanceof ApiError && reason.status === 401);
      setIsReadOnlyHub(false);
      setAuthError(true);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiPost("/api/auth/logout");
    } catch {}
    setStoredAuthToken("", true);
    setUser(null);
    setPermissions([]);
    setRequireAuth(false);
    setIsReadOnlyHub(false);
    await refresh();
    navigate("/");
  }, [navigate, refresh]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <AuthContext.Provider value={{ user, permissions, isLoading, authError, isLoggedIn: !!user, requireAuth, isReadOnlyHub, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
