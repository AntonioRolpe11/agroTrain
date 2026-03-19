import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

import { authFetchJson, getApiBase, setAccessToken } from "@/services/api";

export interface AuthUser {
  id: number;
  email: string;
  nombre: string;
  role: "tecnico" | "administrador";
  is_active: boolean;
}

interface AuthContextType {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const loadProfile = useCallback(async () => {
    try {
      const profile = await authFetchJson<AuthUser>("/api/v1/auth/me");
      setUser(profile);
    } catch {
      setUser(null);
      setAccessToken(null);
      localStorage.removeItem("refresh_token");
    }
  }, []);

  useEffect(() => {
    const refresh = localStorage.getItem("refresh_token");
    if (!refresh) {
      setLoading(false);
      return;
    }
    fetch(`${getApiBase()}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    })
      .then(async (res) => {
        if (!res.ok) throw new Error("refresh failed");
        const data = await res.json();
        setAccessToken(data.access as string);
        if (data.refresh) localStorage.setItem("refresh_token", data.refresh as string);
        return loadProfile();
      })
      .catch(() => {
        localStorage.removeItem("refresh_token");
        setAccessToken(null);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, [loadProfile]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${getApiBase()}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error((data as { detail?: string }).detail ?? "Credenciales incorrectas.");
    }
    const data = await res.json();
    setAccessToken(data.access as string);
    localStorage.setItem("refresh_token", data.refresh as string);
    await loadProfile();
  }, [loadProfile]);

  const logout = useCallback(() => {
    setAccessToken(null);
    localStorage.removeItem("refresh_token");
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, isAdmin: user?.role === "administrador" }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
