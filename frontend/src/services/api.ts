const API_BASE_URL = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8000";

let _accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  _accessToken = token;
}

export function getAccessToken(): string | null {
  return _accessToken;
}

export function getApiBase(): string {
  return API_BASE_URL;
}

async function _doFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  if (_accessToken) {
    headers["Authorization"] = `Bearer ${_accessToken}`;
  }
  return fetch(url, { ...init, headers });
}

async function _tryRefresh(): Promise<boolean> {
  const refresh = localStorage.getItem("refresh_token");
  if (!refresh) return false;
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    if (!res.ok) {
      localStorage.removeItem("refresh_token");
      return false;
    }
    const data = await res.json();
    _accessToken = data.access as string;
    if (data.refresh) localStorage.setItem("refresh_token", data.refresh as string);
    return true;
  } catch {
    return false;
  }
}

export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const url = `${API_BASE_URL}${path}`;
  const res = await _doFetch(url, init);
  if (res.status === 401) {
    const refreshed = await _tryRefresh();
    if (refreshed) {
      return _doFetch(url, init);
    }
  }
  return res;
}

export async function authFetchJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await authFetch(path, init);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${path} -> ${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export async function authPostJson<T>(path: string, payload: unknown): Promise<T> {
  return authFetchJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
