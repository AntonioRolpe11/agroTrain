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

function hasModelGeo(model: ModelMetadata): boolean {
  return Boolean(model.geo?.punto);
}

export default function MisModelos() {
  const { data, isLoading, isError } = useModelosQuery();
  const deleteMut = useDeleteModelo();
  const importMut = useImportModelo();
  const importRef = useRef<HTMLInputElement>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const models = data?.models ?? [];

  async function handleDelete(m: ModelMetadata) {
    if (!confirm(`¿Eliminar el modelo "${m.crop} — ${m.targets.join(", ")}"?`)) return;
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
          <input ref={importRef} type="file" accept=".zip" className="hidden" onChange={handleImport} />
          <Button variant="outline" size="sm" onClick={() => importRef.current?.click()} disabled={importMut.isPending}>
            <Upload className="w-4 h-4 mr-2" />
            {importMut.isPending ? "Importando…" : "Importar ZIP"}
          </Button>
        </div>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando modelos…</p>}
      {isError && <p className="text-sm text-destructive">Error al cargar los modelos.</p>}

      {!isLoading && !isError && models.length === 0 && (
        <div className="text-center py-20 text-muted-foreground text-sm">
          No hay modelos guardados. Entrena uno desde <a href="/validacion-modelo" className="underline">Validación del modelo</a>.
        </div>
      )}

      {models.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40 text-left text-xs font-medium text-muted-foreground">
                <th className="px-4 py-3">Cultivo</th>
                <th className="px-4 py-3">Algoritmo</th>
                <th className="px-4 py-3">Objetivos</th>
                <th className="px-4 py-3">Métricas</th>
                <th className="px-4 py-3">Muestras</th>
                <th className="px-4 py-3">Fecha</th>
                <th className="px-4 py-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m, i) => (
                <tr
                  key={m.model_id}
                  className={`border-b border-border last:border-0 ${i % 2 === 0 ? "" : "bg-muted/20"}`}
                >
                  <td className="px-4 py-3 font-medium">{m.crop}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded font-mono">
                      {m.algorithm}
                    </span>
                    {m.imported && (
                      <span className="ml-1 text-xs bg-purple-50 text-purple-700 px-1.5 py-0.5 rounded">
                        importado
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{m.targets.join(", ")}</td>
                  <td className="px-4 py-3">
                    <MetricsSummary metrics={m.metrics} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{m.n_samples}</td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{fmt(m.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-2">
                      {hasModelGeo(m) ? (
                        <Link to={`/mis-modelos/${m.model_id}/generar-valor`}>
                          <Button variant="outline" size="sm">
                            <Sparkles className="w-3.5 h-3.5 mr-1.5" />
                            Generar valor
                          </Button>
                        </Link>
                      ) : (
                        <Button variant="outline" size="sm" disabled title="Modelo sin ubicación guardada">
                          <Sparkles className="w-3.5 h-3.5 mr-1.5" />
                          Generar valor
                        </Button>
                      )}
                      <a href={modelosApi.getDownloadUrl(m.model_id)} download>
                        <Button variant="outline" size="sm">
                          <Download className="w-3.5 h-3.5 mr-1.5" />
                          ZIP
                        </Button>
                      </a>
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => handleDelete(m)}
                        disabled={deletingId === m.model_id}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
