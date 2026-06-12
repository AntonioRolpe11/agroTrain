// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import {
  authFetch,
  authFetchJson,
  authPostJson,
  getAccessToken,
  getApiBase,
  setAccessToken,
} from "@/services/api";

const originalFetch = globalThis.fetch;

beforeEach(() => {
  setAccessToken(null);
  localStorage.clear();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

function mockResponse(status: number, body: any = {}): Response {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("setAccessToken / getAccessToken", () => {
  it("round-trips the in-memory token", () => {
    expect(getAccessToken()).toBeNull();
    setAccessToken("abc");
    expect(getAccessToken()).toBe("abc");
    setAccessToken(null);
    expect(getAccessToken()).toBeNull();
  });
});

describe("getApiBase", () => {
  it("returns the env-injected base URL or fallback", () => {
    expect(getApiBase()).toMatch(/^https?:\/\//);
  });
});

describe("authFetch", () => {
  it("attaches Authorization header when token set", async () => {
    setAccessToken("xyz");
    const spy = vi.fn().mockResolvedValue(mockResponse(200));
    globalThis.fetch = spy as any;
    await authFetch("/api/v1/foo");
    expect(spy).toHaveBeenCalledTimes(1);
    const [, init] = spy.mock.calls[0];
    expect((init.headers as any).Authorization).toBe("Bearer xyz");
  });

  it("returns response without retry when token absent and 401", async () => {
    const spy = vi.fn().mockResolvedValue(mockResponse(401));
    globalThis.fetch = spy as any;
    const res = await authFetch("/api/v1/foo");
    expect(res.status).toBe(401);
    expect(spy).toHaveBeenCalledTimes(1); // no refresh-token in storage
  });

  it("refreshes on 401 then retries when refresh token present", async () => {
    localStorage.setItem("refresh_token", "r1");
    const calls: string[] = [];
    globalThis.fetch = vi.fn(async (url: any) => {
      calls.push(url);
      if (calls.length === 1) return mockResponse(401); // first call fails
      if (calls.length === 2) return mockResponse(200, { access: "newAccess" }); // refresh
      return mockResponse(200, { ok: true }); // retried call
    }) as any;

    const res = await authFetch("/api/v1/foo");
    expect(res.status).toBe(200);
    expect(calls.length).toBe(3);
    expect(getAccessToken()).toBe("newAccess");
  });

  it("drops refresh token when refresh endpoint rejects", async () => {
    localStorage.setItem("refresh_token", "bad");
    const fetchMock = vi.fn(async (url: any) => {
      if (String(url).includes("/refresh")) return mockResponse(401, "expired");
      return mockResponse(401);
    });
    globalThis.fetch = fetchMock as any;
    const res = await authFetch("/api/v1/foo");
    expect(res.status).toBe(401);
    expect(localStorage.getItem("refresh_token")).toBeNull();
  });
});

describe("authFetchJson", () => {
  it("parses JSON on success", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse(200, { id: 1 })) as any;
    const result = await authFetchJson<{ id: number }>("/api/v1/foo");
    expect(result.id).toBe(1);
  });

  it("throws on non-ok response", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse(500, "boom")) as any;
    await expect(authFetchJson("/api/v1/foo")).rejects.toThrow(/500/);
  });
});

describe("authPostJson", () => {
  it("sets Content-Type and serialises body", async () => {
    const spy = vi.fn().mockResolvedValue(mockResponse(200, { ok: true }));
    globalThis.fetch = spy as any;
    await authPostJson("/api/v1/bar", { name: "x" });
    const [, init] = spy.mock.calls[0];
    expect(init.method).toBe("POST");
    expect((init.headers as any)["Content-Type"]).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ name: "x" }));
  });
});
