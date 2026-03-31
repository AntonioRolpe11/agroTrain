import type { ConfigState } from "@/types/config";
import type {
  ConfigurationsNumberResponse,
  DeadFeaturesResponse,
  FeatureModelNode,
  MunicipioOption,
  MunicipioViewportResponse,
  PartialValidationRequest,
  ProvinciaOption,
  SatisfiableResponse,
  TelemetryExtractRequest,
  TelemetryExtractResponse,
  ValidateFeaturesRequest,
  ValidateResponse,
} from "@/types/api";
import type { Configuracion } from "@/types/api";

import { authFetch, authFetchJson, authPostJson } from "./api";

export const configuratorApi = {
  async validateConfig(config: ConfigState): Promise<ValidateResponse> {
    return authPostJson<ValidateResponse>("/api/v1/configurator/validate", config);
  },

  async validatePartialConfig(payload: PartialValidationRequest): Promise<ValidateResponse> {
    return authPostJson<ValidateResponse>("/api/v1/configurator/validate-partial", payload);
  },

  async getProvincias(): Promise<ProvinciaOption[]> {
    return authFetchJson<ProvinciaOption[]>("/api/v1/geo/provincias");
  },

  async getMunicipios(provinciaId: string): Promise<MunicipioOption[]> {
    return authFetchJson<MunicipioOption[]>(`/api/v1/geo/municipios?provincia_id=${encodeURIComponent(provinciaId)}`);
  },

  async getMunicipioViewport(provinciaId: string, municipioId: string): Promise<MunicipioViewportResponse> {
    return authFetchJson<MunicipioViewportResponse>(
      `/api/v1/geo/municipio-viewport?provincia_id=${encodeURIComponent(provinciaId)}&municipio_id=${encodeURIComponent(municipioId)}`
    );
  },

  async extractTelemetry(payload: TelemetryExtractRequest): Promise<TelemetryExtractResponse> {
    return authPostJson<TelemetryExtractResponse>("/api/v1/telemetry/extract", payload);
  },

  async satisfiable(uvl: string): Promise<SatisfiableResponse> {
    return authPostJson<SatisfiableResponse>("/api/v1/configurator/flamapy/satisfiable", { uvl });
  },

  async configurationsNumber(uvl: string): Promise<ConfigurationsNumberResponse> {
    return authPostJson<ConfigurationsNumberResponse>("/api/v1/configurator/flamapy/configurations-number", { uvl });
  },

  async deadFeatures(uvl: string): Promise<DeadFeaturesResponse> {
    return authPostJson<DeadFeaturesResponse>("/api/v1/configurator/flamapy/dead-features", { uvl });
  },

  async getFeatureModel(): Promise<FeatureModelNode> {
    return authFetchJson<FeatureModelNode>("/api/v1/configurator/model");
  },

  async validateFeatures(payload: ValidateFeaturesRequest): Promise<ValidateResponse> {
    return authPostJson<ValidateResponse>("/api/v1/configurator/validate-features", payload);
  },

  // ------------------------------------------------------------------ configuraciones

  async listConfiguraciones(): Promise<Configuracion[]> {
    return authFetchJson<Configuracion[]>("/api/v1/configurator/configuraciones/");
  },

  async createConfiguracion(payload: { nombre: string; features: string[]; geo: unknown }): Promise<Configuracion> {
    return authPostJson<Configuracion>("/api/v1/configurator/configuraciones/", payload);
  },

  async deleteConfiguracion(id: number): Promise<void> {
    const res = await authFetch(`/api/v1/configurator/configuraciones/${id}/`, { method: "DELETE" });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(`API DELETE configuracion/${id} -> ${res.status}: ${detail}`);
    }
  },
};
