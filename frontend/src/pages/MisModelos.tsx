import { Download, Sparkles, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useDeleteModelo, useImportModelo, useModelosQuery } from "@/hooks/useModelos";
import { modelosApi } from "@/services/modelosApi";
import type { ModelMetadata } from "@/types/api";

function fmt(iso?: string) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function R2Badge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.85 ? "text-green-700 bg-green-50" : value >= 0.7 ? "text-amber-700 bg-amber-50" : "text-red-700 bg-red-50";
  return <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${color}`}>R²={pct}%</span>;
}

function MetricsSummary({ metrics }: { metrics?: ModelMetadata["metrics"] }) {
  const entries = Object.entries(metrics ?? {});
  if (!entries.length) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([target, m]) => (
        <span key={target} className="flex items-center gap-1 text-xs text-muted-foreground">
          <span className="font-medium">{target}</span>
          <R2Badge value={m.r2} />
        </span>
      ))}
    </div>
  );
}

function TypeBadge({ isValidation }: { isValidation?: boolean }) {
  return isValidation === false ? (
    <span className="text-xs bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">digital</span>
  ) : (
    <span className="text-xs bg-teal-50 text-teal-700 px-1.5 py-0.5 rounded">validación</span>
  );
}

function hasModelGeo(model: ModelMetadata): boolean {
  return Boolean(model.geo?.punto);
}

function modelLabel(model: ModelMetadata): string {
  return model.geo?.nombre?.trim() || `#${model.model_id.slice(0, 8)}`;
}

function modelSubtitle(model: ModelMetadata): string | null {
  const muni = model.geo?.municipioNombre?.trim();
  const prov = model.geo?.provinciaNombre?.trim();
  const place = [muni, prov].filter(Boolean).join(", ");
  return place || null;
}

export default function MisModelos() {
  const { data, isLoading, isError } = useModelosQuery();
  const deleteMut = useDeleteModelo();
  const importMut = useImportModelo();
  const importRef = useRef<HTMLInputElement>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const models = data?.models ?? [];

  async function handleDelete(m: ModelMetadata) {
    if (!confirm(`¿Eliminar el modelo "${modelLabel(m)} — ${m.treatment}"?`)) return;
    setDeletingId(m.model_id);
    try {
      await deleteMut.mutateAsync(m.model_id);
      toast.success("Modelo eliminado");
    } catch {
      toast.error("Error al eliminar el modelo");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleDownload(m: ModelMetadata) {
    try {
      await modelosApi.downloadModel(m.model_id);
    } catch {
      toast.error("Error al descargar el modelo");
    }
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    try {
      await importMut.mutateAsync(file);
      toast.success("Modelo importado correctamente");
    } catch {
      toast.error("Error al importar el modelo");
    }
  }

  return (
    <div className="w-full px-[36px] sm:px-[44px] lg:px-[52px] xl:px-[60px] 2xl:px-[400px] py-10">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-serif font-semibold">Mis modelos</h1>
          <p className="text-sm text-muted-foreground mt-1">Modelos entrenados guardados en el servidor</p>
        </div>
        <div>
          <input ref={importRef} data-cy="models-import-input" type="file" accept=".zip" className="hidden" onChange={handleImport} />
          <Button variant="outline" size="sm" data-cy="models-import" onClick={() => importRef.current?.click()} disabled={importMut.isPending}>
            <Upload className="w-4 h-4 mr-2" />
            {importMut.isPending ? "Importando…" : "Importar ZIP"}
          </Button>
        </div>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando modelos…</p>}
      {isError && <p className="text-sm text-destructive">Error al cargar los modelos.</p>}

      {!isLoading && !isError && models.length === 0 && (
        <div className="text-center py-20 text-muted-foreground text-sm">
          No hay modelos guardados. Entrena uno desde <a href="/validacion-modelo" className="underline">Datos y entrenamiento</a>.
        </div>
      )}

      {models.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40 text-left text-xs font-medium text-muted-foreground">
                <th className="px-4 py-3">Parcela</th>
                <th className="px-4 py-3">Tratamiento</th>
                <th className="px-4 py-3">Algoritmo</th>
                <th className="px-4 py-3">Objetivos</th>
                <th className="px-4 py-3">Métricas</th>
                <th className="px-4 py-3">Muestras</th>
                <th className="px-4 py-3">Fecha</th>
                <th className="sticky right-0 z-10 bg-muted px-4 py-3 text-right shadow-[-8px_0_8px_-8px_rgba(0,0,0,0.15)]">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m, i) => {
                const rowBg = i % 2 === 0 ? "bg-background" : "bg-muted";
                return (
                <tr
                  key={m.model_id}
                  data-cy="model-row"
                  data-cy-model-id={m.model_id}
                  className={`border-b border-border last:border-0 ${rowBg}`}
                >
                  <td className="px-4 py-3">
                    <div className="flex flex-col gap-0.5">
                      <span className="font-medium">{modelLabel(m)}</span>
                      {modelSubtitle(m) && (
                        <span className="text-xs text-muted-foreground">{modelSubtitle(m)}</span>
                      )}
                      <span className="font-mono text-[10px] text-muted-foreground/70">{m.model_id.slice(0, 8)}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 font-medium">{m.treatment}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded font-mono">
                      {m.algorithm}
                    </span>
                    {m.imported && (
                      <span className="ml-1 text-xs bg-purple-50 text-purple-700 px-1.5 py-0.5 rounded">
                        importado
                      </span>
                    )}
                    <span className="ml-1"><TypeBadge isValidation={m.is_validation} /></span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{m.targets.join(", ")}</td>
                  <td className="px-4 py-3">
                    {m.is_validation === false ? (
                      <span className="text-xs text-muted-foreground">Sin validación · 100% datos</span>
                    ) : (
                      <MetricsSummary metrics={m.metrics} />
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{m.n_samples}</td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{fmt(m.created_at)}</td>
                  <td className={`sticky right-0 z-10 px-4 py-3 shadow-[-8px_0_8px_-8px_rgba(0,0,0,0.15)] ${rowBg}`}>
                    <div className="flex items-center justify-end gap-2">
                      {hasModelGeo(m) ? (
                        <Link to={`/mis-modelos/${m.model_id}/generar-valor`} data-cy="model-generar">
                          <Button variant="outline" size="sm">
                            <Sparkles className="w-3.5 h-3.5 mr-1.5" />
                            Generar valor
                          </Button>
                        </Link>
                      ) : (
                        <Button variant="outline" size="sm" data-cy="model-generar-disabled" disabled title="Modelo sin ubicación guardada">
                          <Sparkles className="w-3.5 h-3.5 mr-1.5" />
                          Generar valor
                        </Button>
                      )}
                      <Button variant="outline" size="sm" data-cy="model-download" onClick={() => handleDownload(m)}>
                        <Download className="w-3.5 h-3.5 mr-1.5" />
                        ZIP
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        data-cy="model-delete"
                        className="text-destructive hover:text-destructive"
                        onClick={() => handleDelete(m)}
                        disabled={deletingId === m.model_id}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
