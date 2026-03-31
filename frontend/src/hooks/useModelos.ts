import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { modelosApi } from "@/services/modelosApi";

export function useModelosQuery() {
  return useQuery({
    queryKey: ["modelos"],
    queryFn: () => modelosApi.listModels(),
  });
}

export function useDeleteModelo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (modelId: string) => modelosApi.deleteModel(modelId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modelos"] }),
  });
}

export function useImportModelo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (zip: Blob) => modelosApi.importModel(zip),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modelos"] }),
  });
}
