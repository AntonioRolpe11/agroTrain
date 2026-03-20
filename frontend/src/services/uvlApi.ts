import type {
  FeatureModelNode,
  UVLActivateResponse,
  UVLPreviewActivationReport,
  UVLValidateResponse,
  UVLVersionDetail,
  UVLVersionSummary,
} from "@/types/api";

import { authFetch, authFetchJson, authPostJson } from "./api";

export const uvlApi = {
  listVersions(): Promise<UVLVersionSummary[]> {
    return authFetchJson<UVLVersionSummary[]>("/api/v1/uvl/versions/");
  },

  getVersion(id: number): Promise<UVLVersionDetail> {
    return authFetchJson<UVLVersionDetail>(`/api/v1/uvl/versions/${id}/`);
  },

  validateTree(tree: FeatureModelNode, constraintsText: string): Promise<UVLValidateResponse> {
    return authPostJson<UVLValidateResponse>("/api/v1/uvl/versions/validate/", {
      tree,
      constraints_text: constraintsText,
    });
  },

  createVersion(
    name: string,
    description: string,
    tree: FeatureModelNode,
    constraintsText: string,
  ): Promise<UVLVersionSummary> {
    return authPostJson<UVLVersionSummary>("/api/v1/uvl/versions/create/", {
      name,
      description,
      tree,
      constraints_text: constraintsText,
    });
  },

  previewActivation(id: number): Promise<UVLPreviewActivationReport> {
    return authFetchJson<UVLPreviewActivationReport>(`/api/v1/uvl/versions/${id}/preview-activation/`);
  },

  activateVersion(id: number, confirmIncompatible: boolean): Promise<UVLActivateResponse> {
    return authPostJson<UVLActivateResponse>(`/api/v1/uvl/versions/${id}/activate/`, {
      confirm_incompatible: confirmIncompatible,
    });
  },

  async deleteVersion(id: number): Promise<void> {
    const res = await authFetch(`/api/v1/uvl/versions/${id}/`, { method: "DELETE" });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error((body as { detail?: string }).detail ?? res.statusText);
    }
  },
};
