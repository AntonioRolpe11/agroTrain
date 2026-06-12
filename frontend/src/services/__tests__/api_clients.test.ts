// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { setAccessToken } from "@/services/api";
import { configuratorApi } from "@/services/configuratorApi";
import { modelosApi } from "@/services/modelosApi";
import { uvlApi } from "@/services/uvlApi";

const originalFetch = globalThis.fetch;

function mockJson(status: number, body: any) {
  // 204 must not have a body
  if (status === 204) {
    return new Response(null, { status });
  }
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function alwaysJson(status: number, body: any) {
  // Return a fresh response per call so multiple awaits in one test don't reuse a consumed body.
  return vi.fn(async () => mockJson(status, body));
}

beforeEach(() => setAccessToken("t"));
afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("configuratorApi", () => {
  it("encodes provincia_id in getMunicipios", async () => {
    const spy = vi.fn().mockResolvedValue(mockJson(200, []));
    globalThis.fetch = spy as any;
    await configuratorApi.getMunicipios("41");
    expect(spy.mock.calls[0][0]).toContain("provincia_id=41");
  });

  it("hits POST /flamapy/satisfiable", async () => {
    const spy = vi.fn().mockResolvedValue(mockJson(200, { satisfiable: true }));
    globalThis.fetch = spy as any;
    const result = await configuratorApi.satisfiable("");
    expect(spy.mock.calls[0][1]?.method).toBe("POST");
    expect(result.satisfiable).toBe(true);
  });

  it("hits configurations-number and dead-features endpoints", async () => {
    globalThis.fetch = alwaysJson(200, {}) as any;
    await configuratorApi.configurationsNumber("");
    await configuratorApi.deadFeatures("");
  });

  it("lists, creates and deletes configuraciones", async () => {
    globalThis.fetch = alwaysJson(200, []) as any;
    await configuratorApi.listConfiguraciones();
    await configuratorApi.createConfiguracion({ nombre: "x", features: [], geo: {} });
    await configuratorApi.deleteConfiguracion(1);
  });

  it("raises when delete returns non-ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockJson(500, "boom")) as any;
    await expect(configuratorApi.deleteConfiguracion(1)).rejects.toThrow(/500/);
  });

  it("getProvincias, getMunicipioViewport, getFeatureModel, validateFeatures, extractTelemetry", async () => {
    globalThis.fetch = alwaysJson(200, []) as any;
    await configuratorApi.getProvincias();
    await configuratorApi.getMunicipioViewport("41", "41001");
    await configuratorApi.getFeatureModel();
    await configuratorApi.validateFeatures({ features: [], is_full: true, step: "full" });
    await configuratorApi.extractTelemetry({} as any);
  });
});

describe("modelosApi", () => {
  it("train posts multipart with features and geo", async () => {
    const spy = vi.fn().mockResolvedValue(mockJson(202, { model_id: "x" }));
    globalThis.fetch = spy as any;
    const blob = new Blob(["a;b\n1;2"], { type: "text/csv" });
    await modelosApi.train(["A", "B"], blob, { lat: 1, lng: 2 });
    const [, init] = spy.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("train throws on non-ok response", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockJson(400, "boom")) as any;
    await expect(modelosApi.train([], new Blob([]))).rejects.toThrow(/400/);
  });

  it("status / list / get / predictions / download URL", async () => {
    globalThis.fetch = alwaysJson(200, {}) as any;
    await modelosApi.getStatus("m");
    await modelosApi.listModels();
    await modelosApi.getModel("m");
    await modelosApi.listPredictions("m");
    expect(modelosApi.getDownloadUrl("m")).toMatch(/\/api\/v1\/modelos\/m\/download/);
  });

  it("predict throws on non-ok", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockJson(409, "dup")) as any;
    await expect(modelosApi.predict("m", new Blob([]))).rejects.toThrow(/409/);
  });

  it("importModel posts multipart and surfaces errors", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockJson(403, "no")) as any;
    await expect(modelosApi.importModel(new Blob([]))).rejects.toThrow(/403/);
  });

  it("deleteModel succeeds and throws on error", async () => {
    globalThis.fetch = alwaysJson(200, {}) as any;
    await modelosApi.deleteModel("m");

    globalThis.fetch = vi.fn().mockResolvedValue(mockJson(404, "")) as any;
    await expect(modelosApi.deleteModel("m")).rejects.toThrow();
  });
});

describe("uvlApi", () => {
  it("listVersions / getVersion / preview / activate / validate / create", async () => {
    globalThis.fetch = alwaysJson(200, {}) as any;
    await uvlApi.listVersions();
    await uvlApi.getVersion(1);
    await uvlApi.previewActivation(1);
    await uvlApi.activateVersion(1, false);
    await uvlApi.validateTree({} as any, "");
    await uvlApi.createVersion("n", "d", {} as any, "");
  });

  it("deleteVersion succeeds when 2xx", async () => {
    globalThis.fetch = alwaysJson(200, {}) as any;
    await uvlApi.deleteVersion(1);
  });

  it("deleteVersion throws structured error", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockJson(409, { detail: "active" })) as any;
    await expect(uvlApi.deleteVersion(1)).rejects.toThrow(/active/);
  });
});
