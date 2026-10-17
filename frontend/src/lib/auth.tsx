import { createContext, useContext, useState, type ReactNode } from "react";
import { clearSession, getRole, getToken, setSession } from "./api";
import type { UserRole } from "./types";

interface AuthContextValue {
  token: string | null;
  role: UserRole | null;
  isAuthenticated: boolean;
  login: (token: string, role: UserRole) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(getToken());
  const [role, setRole] = useState<UserRole | null>(getRole() as UserRole | null);

  const login = (newToken: string, newRole: UserRole) => {
    setSession(newToken, newRole);
    setToken(newToken);
    setRole(newRole);
  };

  const logout = () => {
    clearSession();
    setToken(null);
    setRole(null);
  };

  return (
    <AuthContext.Provider value={{ token, role, isAuthenticated: !!token, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
