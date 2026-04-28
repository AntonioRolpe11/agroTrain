import { type ChangeEvent } from "react";
import { type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusTag } from "@/components/ui/StatusTag";
import type { CsvDataset, CsvKind } from "@/lib/csvDataset";

function getDatasetTone(dataset: CsvDataset | null, warnings: string[]) {
  if (!dataset) return "neutral" as const;
  if (dataset.errors.length > 0) return "warning" as const;
  if (warnings.length > 0 || dataset.rowsWithMissingValues > 0) return "warning" as const;
  return "success" as const;
}

interface CsvUploadSectionProps {
  title: string;
  description: string;
  kind: CsvKind;
  icon: LucideIcon;
  expectedColumns: readonly string[];
  dataset: CsvDataset | null;
  warnings: string[];
  onUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  onClear: () => void;
  showUploadControls?: boolean;
}

export function CsvUploadSection({
  title, description, kind, icon: Icon, expectedColumns, dataset, warnings, onUpload, onClear, showUploadControls = true,
}: CsvUploadSectionProps) {
  const tone = getDatasetTone(dataset, warnings);
  const totalEmptyCells = dataset ? Object.values(dataset.emptyValueCounts).reduce((a, b) => a + b, 0) : 0;

  return (
    <div className="rounded-xl border border-border bg-background/70 p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-lg bg-primary/10 p-2 text-olive"><Icon className="h-5 w-5" /></div>
          <div>
            <h3 className="text-lg font-semibold">{title}</h3>
            <p className="text-sm text-muted-foreground">{description}</p>
          </div>
        </div>
        <StatusTag tone={tone}>
          {!dataset ? "Opcional" : dataset.errors.length > 0 ? "Con incidencias"
            : warnings.length > 0 || dataset.rowsWithMissingValues > 0 ? "Revisado" : "Listo"}
        </StatusTag>
      </div>
      <div className="space-y-4">
        {showUploadControls && (
          <div>
            <Label htmlFor={`${kind}-csv`} className="mb-2 block">Subir archivo CSV</Label>
            <Input id={`${kind}-csv`} type="file" accept=".csv,text/csv" onChange={onUpload} />
          </div>
        )}
        {!dataset && (
          <div className="rounded-lg border border-dashed border-border bg-muted/20 p-4 text-sm text-muted-foreground">
            No has cargado ningún archivo. Si lo dejas vacío, esta fuente usará datos predeterminados del sistema.
          </div>
        )}
        {dataset && (
          <>
            <div className="grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
              <div><span className="text-muted-foreground">Archivo:</span><p className="break-all font-medium">{dataset.fileName}</p></div>
              <div><span className="text-muted-foreground">Filas detectadas:</span><p className="font-medium">{dataset.rowCount}</p></div>
              <div><span className="text-muted-foreground">Separador:</span><p className="font-medium">{dataset.delimiter === ";" ? "Punto y coma (;)" : "Coma (,)"}</p></div>
              <div><span className="text-muted-foreground">Columnas reconocidas:</span><p className="font-medium">{dataset.recognizedDataColumns.length} / {expectedColumns.length - 1}</p></div>
            </div>
            {dataset.errors.length > 0 && (
              <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">
                <ul className="list-disc space-y-1 pl-5">{dataset.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
              </div>
            )}
            {(warnings.length > 0 || dataset.rowsWithMissingValues > 0 || totalEmptyCells > 0) && (
              <div className="rounded-lg border border-satellite-amber/20 bg-satellite-amber/10 p-4 text-sm text-satellite-amber">
                <ul className="list-disc space-y-1 pl-5">
                  {warnings.map((w, i) => <li key={i}>{w}</li>)}
                  {dataset.rowsWithMissingValues > 0 && <li>{dataset.rowsWithMissingValues} filas con al menos una celda vacía.</li>}
                  {totalEmptyCells > 0 && <li>{totalEmptyCells} celdas vacías en total.</li>}
                </ul>
              </div>
            )}
            <Button type="button" variant="outline" size="sm" onClick={onClear}>Quitar archivo</Button>
          </>
        )}
      </div>
    </div>
  );
}
