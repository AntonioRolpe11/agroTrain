import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { modelosApi } from "@/services/modelosApi";
import type { ModelMetadata, PredictionHistoryItem, PredictionResponse, TrainingStatus } from "@/types/api";

const POLL_INTERVAL_MS = 3000;

export const modelosQueryKeys = {
  all: ["modelos"] as const,
  list: () => [...modelosQueryKeys.all, "list"] as const,
  status: (modelId: string | null) => [...modelosQueryKeys.all, "status", modelId ?? "none"] as const,
  detail: (modelId: string | null) => [...modelosQueryKeys.all, "detail", modelId ?? "none"] as const,
  predictions: (modelId: string | null) => [...modelosQueryKeys.all, "predictions", modelId ?? "none"] as const,
};

// Lanza entrenamiento; devuelve { model_id } inmediatamente (202)
export function useTrainModelMutation() {
  return useMutation({
    mutationFn: ({ features, csvBlob, geo }: { features: string[]; csvBlob: Blob; geo?: unknown }) =>
      modelosApi.train(features, csvBlob, geo),
    retry: 0,
  });
}

// Polling de estado — se detiene automáticamente cuando el entrenamiento termina
export function useTrainingStatusQuery(modelId: string | null) {
  return useQuery<TrainingStatus>({
    queryKey: modelosQueryKeys.status(modelId),
    queryFn: () => modelosApi.getStatus(modelId!),
    enabled: Boolean(modelId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "completed" || status === "error") return false;
      return POLL_INTERVAL_MS;
    },
    refetchIntervalInBackground: true,
    retry: 1,
  });
}

// Lista todos los modelos guardados en disco
export function useModelsListQuery() {
  return useQuery<{ models: ModelMetadata[] }>({
    queryKey: modelosQueryKeys.list(),
    queryFn: modelosApi.listModels,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
}

export function useModelDetailQuery(modelId: string | null) {
  return useQuery<ModelMetadata>({
    queryKey: modelosQueryKeys.detail(modelId),
    queryFn: () => modelosApi.getModel(modelId!),
    enabled: Boolean(modelId),
    staleTime: 10_000,
    retry: 1,
  });
}

export function usePredictModelMutation() {
  const queryClient = useQueryClient();
  return useMutation<PredictionResponse, Error, { modelId: string; csvBlob: Blob }>({
    mutationFn: ({ modelId, csvBlob }) => modelosApi.predict(modelId, csvBlob),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: modelosQueryKeys.predictions(variables.modelId) });
    },
    retry: 0,
  });
}

export function usePredictionHistoryQuery(modelId: string | null) {
  return useQuery<{ predictions: PredictionHistoryItem[] }>({
    queryKey: modelosQueryKeys.predictions(modelId),
    queryFn: () => modelosApi.listPredictions(modelId!),
    enabled: Boolean(modelId),
    staleTime: 10_000,
    retry: 1,
  });
}

export function useDeleteModelMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (modelId: string) => modelosApi.deleteModel(modelId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: modelosQueryKeys.list() });
    },
    retry: 0,
  });
}

export function useImportModelMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (zipBlob: Blob) => modelosApi.importModel(zipBlob),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: modelosQueryKeys.list() });
    },
    retry: 0,
  });
}
