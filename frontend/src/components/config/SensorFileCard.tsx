import { useRef } from "react";
import { Upload, X, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import type { GenericCsvDataset } from "@/lib/csvDataset";

interface SensorFileCardProps {
  label: string;
  icon: LucideIcon;
  required: boolean;
  dataset: GenericCsvDataset | null;
  timestampCol: string;
  dataCol: string;
  isLoading: boolean;
  onUpload: (file: File) => void;
  onClear: () => void;
  onTimestampColChange: (col: string) => void;
  onDataColChange: (col: string) => void;
}

type CardTone = "optional" | "missing" | "error" | "pending" | "ready";

function getTone(required: boolean, dataset: GenericCsvDataset | null, timestampCol: string, dataCol: string): CardTone {
  if (!dataset) return required ? "missing" : "optional";
  if (dataset.errors.length > 0) return "error";
  if (!timestampCol || !dataCol) return "pending";
  return "ready";
}

const toneStyles: Record<CardTone, string> = {
  ready: "border-sensor-green/30",
  pending: "border-satellite-amber/30",
  missing: "border-destructive/30",
  error: "border-destructive/30",
  optional: "border-border",
};

const tagStyles: Record<CardTone, string> = {
  ready: "border-sensor-green/25 bg-sensor-green/10 text-sensor-green",
  pending: "border-satellite-amber/25 bg-satellite-amber/10 text-satellite-amber",
  missing: "border-destructive/25 bg-destructive/10 text-destructive",
  error: "border-destructive/25 bg-destructive/10 text-destructive",
  optional: "border-border bg-muted/40 text-muted-foreground",
};

const tagLabels: Record<CardTone, string> = {
  ready: "Listo",
  pending: "Vincular columnas",
  missing: "Requerido",
  error: "Error",
  optional: "Opcional",
};

export function SensorFileCard({
  label,
  icon: Icon,
  required,
  dataset,
  timestampCol,
  dataCol,
  isLoading,
  onUpload,
  onClear,
  onTimestampColChange,
  onDataColChange,
}: SensorFileCardProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const tone = getTone(required, dataset, timestampCol, dataCol);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) onUpload(file);
    e.target.value = "";
  };

  return (
    <div data-cy="sensor-card" data-cy-label={label} className={`rounded-lg border bg-background/70 p-4 ${toneStyles[tone]}`}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-sensor-green" />
          <span className="text-sm font-medium">{label}</span>
        </div>
        <div className="flex items-center gap-2">
          <span data-cy="sensor-tone" className={`rounded-full border px-2 py-0.5 text-xs font-medium ${tagStyles[tone]}`}>
            {tagLabels[tone]}
          </span>
          {dataset && (
            <Button type="button" variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={onClear}>
              <X className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>

      {!dataset ? (
        <>
          <input
            ref={inputRef}
            data-cy="sensor-file-input"
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={handleChange}
            disabled={isLoading}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={isLoading}
          >
            <Upload className="mr-2 h-3.5 w-3.5" />
            {isLoading ? "Procesando..." : "Subir CSV"}
          </Button>
        </>
      ) : (
        <div className="space-y-3">
          <p className="break-all text-xs text-muted-foreground">
            {dataset.fileName} · {dataset.rowCount} filas
          </p>

          {dataset.errors.length > 0 ? (
            <ul className="list-disc space-y-0.5 pl-4 text-xs text-destructive">
              {dataset.errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          ) : (
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="space-y-1">
                <Label className="text-xs">Columna de fecha/hora</Label>
                <select
                  data-cy="sensor-timestamp-col"
                  className={`w-full rounded-md border bg-background px-2 py-1.5 text-xs transition-colors ${
                    timestampCol ? "border-sensor-green/40 text-foreground" : "border-satellite-amber/40 text-muted-foreground"
                  }`}
                  value={timestampCol}
                  onChange={(e) => onTimestampColChange(e.target.value)}
                >
                  <option value="">— Seleccionar —</option>
                  {dataset.headers.map((h) => (
                    <option key={h} value={h}>
                      {h}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Columna de dato</Label>
                <select
                  data-cy="sensor-data-col"
                  className={`w-full rounded-md border bg-background px-2 py-1.5 text-xs transition-colors ${
                    dataCol ? "border-sensor-green/40 text-foreground" : "border-satellite-amber/40 text-muted-foreground"
                  }`}
                  value={dataCol}
                  onChange={(e) => onDataColChange(e.target.value)}
                >
                  <option value="">— Seleccionar —</option>
                  {dataset.headers.map((h) => (
                    <option key={h} value={h}>
                      {h}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {dataset.warnings.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-4 text-xs text-satellite-amber">
              {dataset.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
