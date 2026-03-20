import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { configuratorApi } from "@/services/configuratorApi";

const QUERY_KEY = ["configuraciones"];

export function useConfiguracionesQuery() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => configuratorApi.listConfiguraciones(),
  });
}

export function useGuardarConfiguracion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { nombre: string; features: string[]; geo: unknown }) =>
      configuratorApi.createConfiguracion(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
}

export function useEliminarConfiguracion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => configuratorApi.deleteConfiguracion(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
}
