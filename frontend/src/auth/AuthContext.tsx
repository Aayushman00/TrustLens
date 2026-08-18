import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  apiFetch,
  clearTokens,
  getAccessToken,
  setAuthFailureHandler,
  storeTokens,
} from "../api/client";
import type { TokenResponse, UserRead } from "../api/types";

interface AuthContextValue {
  user: UserRead | null;
  /** True while the stored session is being restored on first load. */
  initializing: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserRead | null>(null);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    setAuthFailureHandler(() => setUser(null));
    return () => setAuthFailureHandler(null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function restore() {
      if (!getAccessToken()) {
        setInitializing(false);
        return;
      }
      try {
        const me = await apiFetch<UserRead>("/v1/auth/me");
        if (!cancelled) setUser(me);
      } catch {
        clearTokens();
      } finally {
        if (!cancelled) setInitializing(false);
      }
    }
    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await apiFetch<TokenResponse>("/v1/auth/login", {
      method: "POST",
      body: { email, password },
      anonymous: true,
    });
    storeTokens(tokens);
    setUser(await apiFetch<UserRead>("/v1/auth/me"));
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, initializing, login, logout }),
    [user, initializing, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
