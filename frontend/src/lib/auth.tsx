import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, tokenStore } from "./api";

export type User = { id: string; name: string; email: string };
type AuthResp = { token: string; user: User };

type AuthCtx = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tokenStore.get()) { setLoading(false); return; }
    api<User>("/api/auth/me").then(setUser).catch(() => tokenStore.set(null)).finally(() => setLoading(false));
  }, []);

  const finish = (r: AuthResp) => { tokenStore.set(r.token); setUser(r.user); };
  const login = useCallback(async (email: string, password: string) => {
    finish(await api<AuthResp>("/api/auth/login", { method: "POST", json: { email, password } }));
  }, []);
  const register = useCallback(async (name: string, email: string, password: string) => {
    finish(await api<AuthResp>("/api/auth/register", { method: "POST", json: { name, email, password } }));
  }, []);
  const logout = useCallback(() => { tokenStore.set(null); setUser(null); }, []);

  return <Ctx.Provider value={{ user, loading, login, register, logout }}>{children}</Ctx.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
