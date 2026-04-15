import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useLocation } from "wouter";
import { apiGet, ApiError } from "@/lib/api";

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
      await apiGet<{ total_files: number }>("/api/stats");
      setUser(null);
      setRequireAuth(false);
    } catch (reason: unknown) {
      setUser(null);
      if (reason instanceof ApiError && reason.status === 401) {
        setRequireAuth(true);
      } else {
        setRequireAuth(false);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    setUser(null);
    navigate("/");
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
