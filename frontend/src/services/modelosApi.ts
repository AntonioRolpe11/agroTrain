import type {
  ModelMetadata,
  PredictionHistoryItem,
  PredictionResponse,
  TrainStartResponse,
  TrainingStatus,
} from "@/types/api";

import { authFetch, authFetchJson, getApiBase } from "./api";

export const modelosApi = {
  async train(features: string[], csvBlob: Blob, geo?: unknown, isValidation = true): Promise<TrainStartResponse> {
    const form = new FormData();
    form.append("features", JSON.stringify(features));
    if (geo !== undefined) form.append("geo", JSON.stringify(geo));
    form.append("is_validation", String(isValidation));
    form.append("csv_file", csvBlob, "datos_fusionados.csv");

    const response = await authFetch("/api/v1/modelos/train", {
      method: "POST",
      body: form,
    });

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`${response.status}: ${detail}`);
    }
    return response.json() as Promise<TrainStartResponse>;
  },

  getStatus(modelId: string): Promise<TrainingStatus> {
    return authFetchJson<TrainingStatus>(`/api/v1/modelos/${modelId}/status`);
  },

  listModels(): Promise<{ models: ModelMetadata[] }> {
    return authFetchJson<{ models: ModelMetadata[] }>("/api/v1/modelos/");
  },

  getModel(modelId: string): Promise<ModelMetadata> {
    return authFetchJson<ModelMetadata>(`/api/v1/modelos/${modelId}/`);
  },

  async predict(modelId: string, csvBlob: Blob): Promise<PredictionResponse> {
    const form = new FormData();
    form.append("csv_file", csvBlob, "datos_prediccion.csv");

    const response = await authFetch(`/api/v1/modelos/${modelId}/predict`, {
      method: "POST",
      body: form,
    });

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`${response.status}: ${detail}`);
    }
    return response.json() as Promise<PredictionResponse>;
  },

  listPredictions(modelId: string): Promise<{ predictions: PredictionHistoryItem[] }> {
    return authFetchJson<{ predictions: PredictionHistoryItem[] }>(`/api/v1/modelos/${modelId}/predictions`);
  },

  getDownloadUrl(modelId: string): string {
    return `${getApiBase()}/api/v1/modelos/${modelId}/download`;
  },

  async importModel(zipBlob: Blob): Promise<ModelMetadata> {
    const form = new FormData();
    form.append("zip_file", zipBlob, "modelo.zip");

    const response = await authFetch("/api/v1/modelos/import", {
      method: "POST",
      body: form,
    });

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`${response.status}: ${detail}`);
    }
    return response.json() as Promise<ModelMetadata>;
  },

  async deleteModel(modelId: string): Promise<void> {
    const response = await authFetch(`/api/v1/modelos/${modelId}/`, { method: "DELETE" });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`${response.status}: ${detail}`);
    }
  },
};
