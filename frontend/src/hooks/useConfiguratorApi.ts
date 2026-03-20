import { useMutation, useQuery } from "@tanstack/react-query";

import { configuratorApi } from "@/services/configuratorApi";
import type {
  FeatureModelNode,
  MunicipioViewportResponse,
  PartialValidationRequest,
  ProvinciaOption,
  TelemetryExtractRequest,
  ValidateFeaturesRequest,
  ValidateResponse,
} from "@/types/api";
import type { ConfigState } from "@/types/config";

const GEO_STALE_TIME = 5 * 60 * 1000;

export const geoQueryKeys = {
  all: ["geo"] as const,
  provincias: () => [...geoQueryKeys.all, "provincias"] as const,
  municipios: (provinciaId: string | null | undefined) =>
    [...geoQueryKeys.all, "municipios", provinciaId ?? "none"] as const,
  municipioViewport: (provinciaId: string | null | undefined, municipioId: string | null | undefined) =>
    [...geoQueryKeys.all, "municipio-viewport", provinciaId ?? "none", municipioId ?? "none"] as const,
};

function createMutationOptions<TData, TVariables>(
  mutationFn: (variables: TVariables) => Promise<TData>,
) {
  return {
    mutationFn,
    retry: 0,
  };
}

export function useProvinciasQuery() {
  return useQuery<ProvinciaOption[]>({
    queryKey: geoQueryKeys.provincias(),
    queryFn: configuratorApi.getProvincias,
    staleTime: GEO_STALE_TIME,
    refetchOnWindowFocus: false,
  });
}

export function useMunicipiosQuery(provinciaId: string | null | undefined) {
  return useQuery({
    queryKey: geoQueryKeys.municipios(provinciaId),
    queryFn: () => configuratorApi.getMunicipios(provinciaId as string),
    enabled: Boolean(provinciaId),
    staleTime: GEO_STALE_TIME,
    refetchOnWindowFocus: false,
  });
}

export function useMunicipioViewportQuery(
  provinciaId: string | null | undefined,
  municipioId: string | null | undefined,
  enabled = true,
) {
  return useQuery<MunicipioViewportResponse>({
    queryKey: geoQueryKeys.municipioViewport(provinciaId, municipioId),
    queryFn: () => configuratorApi.getMunicipioViewport(provinciaId as string, municipioId as string),
    enabled: enabled && Boolean(provinciaId) && Boolean(municipioId),
    staleTime: GEO_STALE_TIME,
    refetchOnWindowFocus: false,
  });
}

export function useValidateConfigMutation() {
  return useMutation<ValidateResponse, Error, ConfigState>(
    createMutationOptions((config) => configuratorApi.validateConfig(config)),
  );
}

export function useValidatePartialConfigMutation() {
  return useMutation<ValidateResponse, Error, PartialValidationRequest>(
    createMutationOptions((payload) => configuratorApi.validatePartialConfig(payload)),
  );
}

export function useExtractTelemetryMutation() {
  return useMutation(
    createMutationOptions((payload: TelemetryExtractRequest) => configuratorApi.extractTelemetry(payload)),
  );
}

export function useValidateFeaturesMutation() {
  return useMutation<ValidateResponse, Error, ValidateFeaturesRequest>(
    createMutationOptions((payload) => configuratorApi.validateFeatures(payload)),
  );
}

export const featureModelQueryKey = ["feature-model"] as const;

export function useFeatureModelQuery() {
  return useQuery<FeatureModelNode>({
    queryKey: featureModelQueryKey,
    queryFn: configuratorApi.getFeatureModel,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}
