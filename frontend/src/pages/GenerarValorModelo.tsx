import { useMemo, useState } from "react";
import { AlertTriangle, ArrowLeft, CheckCircle2, GitMerge, History, Loader2, Play, Satellite, Sparkles, Thermometer, TreeDeciduous } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { SensorFileCard } from "@/components/config/SensorFileCard";
import { SensorLocationMap } from "@/components/results/SensorLocationMap";
import { TelemetryPreview } from "@/components/results/TelemetryPreview";
import { Button } from "@/components/ui/button";
import { StatusTag } from "@/components/ui/StatusTag";
import { useExtractTelemetryMutation, useFeatureModelQuery } from "@/hooks/useConfiguratorApi";
import { useModelDetailQuery, usePredictionHistoryQuery, usePredictModelMutation } from "@/hooks/useModelosApi";
import { calculateDendroParams } from "@/lib/dendroCalc";
import { fuseSensorAndTelemetry, fusionResultToCsv, type FusionResult } from "@/lib/dataFusion";
import { parseCsvFileGeneric, type GenericCsvDataset } from "@/lib/csvDataset";
import { mergeSensorFiles, type SensorFileInput } from "@/lib/sensorMerger";
import { buildCsvColumnInfo, collectCsvFeatures, getNode, getRelationChildren } from "@/utils/featureModel";

const TARGET_SENSOR_COLS = new Set(["MCD", "TasaBuenos", "TasaSeveros"]);
const TEMPERATURE_FEATURE_ID = "TemperaturaAire";
const CHART_COLORS = ["#4a7c3f", "#d97706", "#2563eb", "#dc2626", "#7c3aed", "#0891b2"];

function getCsvCols(node: { attributes?: Record<string, unknown> } | null): string[] {
  const attrs = node?.attributes ?? {};
  if (attrs.csv_col) return [String(attrs.csv_col)];
  if (attrs.csv_cols) return String(attrs.csv_cols).split(",").map((s) => s.trim()).filter(Boolean);
  return [];
}

interface SensorFileEntry {
  dataset: GenericCsvDataset | null;
  timestampCol: string;
  dataCol: string;
  isLoading: boolean;
}

const emptyEntry = (): SensorFileEntry => ({ dataset: null, timestampCol: "", dataCol: "", isLoading: false });

function fmt(iso?: string) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDate(dateStr: string | number) {
  const s = String(dateStr);
  const [y, m, d] = s.split("-");
  if (!y || !m || !d) return s;
  return `${d}/${m}/${y}`;
}

function addOneDay(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().split("T")[0];
}

function getDateRangeFromRows(rows: Array<Record<string, unknown>>): [string, string] | null {
  const dates = rows.map((r) => String(r.date ?? "")).filter(Boolean).sort();
  return dates.length ? [dates[0], dates[dates.length - 1]] : null;
}

export default function GenerarValorModelo() {
  const { modelId } = useParams();
  const modelQuery = useModelDetailQuery(modelId ?? null);
  const historyQuery = usePredictionHistoryQuery(modelId ?? null);
  const featureModelQuery = useFeatureModelQuery();
  const extractTelemetryMutation = useExtractTelemetryMutation();
  const predictMutation = usePredictModelMutation();

  const model = modelQuery.data ?? null;
  const featureModel = featureModelQuery.data ?? null;
  const features = useMemo(() => model?.features ?? [], [model]);
  const geo = model?.geo ?? {};
  const punto = geo.punto ?? null;
  const cloudThreshold = typeof geo.cloudThreshold === "number" ? geo.cloudThreshold : 20;

  const requiredCols = useMemo(() => new Set(model?.all_cols ?? []), [model]);
  const telemetryColumnInfo = useMemo(
    () => featureModel ? buildCsvColumnInfo(featureModel, "DatosTelemetria") : { aliases: {} as Record<string, string>, dataColumns: [] as string[] },
    [featureModel],
  );
  const selectedTelemetry = useMemo(
    () => telemetryColumnInfo.dataColumns.filter((col) => requiredCols.has(col)),
    [requiredCols, telemetryColumnInfo],
  );
  const dendroSensors = useMemo(() => {
    const dendroNode = featureModel ? getNode(featureModel, "Dendrometro") : null;
    return dendroNode
      ? getRelationChildren(dendroNode)
          .map((node) => ({ featureName: node.name, csvCol: getCsvCols(node)[0] ?? node.name }))
          .filter((sensor) => requiredCols.has(sensor.csvCol))
      : [];
  }, [featureModel, requiredCols]);
  const excludedSensorIds = useMemo(
    () => new Set([...dendroSensors.map((sensor) => sensor.featureName), TEMPERATURE_FEATURE_ID]),
    [dendroSensors],
  );
  const genericSensors = useMemo(
    () => featureModel && model
      ? collectCsvFeatures(featureModel, features, excludedSensorIds).filter((s) => requiredCols.has(s.csvCol))
      : [],
    [featureModel, features, model, requiredCols, excludedSensorIds],
  );

  const requiredTargetCols = useMemo(
    () => [...TARGET_SENSOR_COLS].filter((col) => requiredCols.has(col)),
    [requiredCols],
  );
  const dendroRequired = requiredTargetCols.length > 0;
  const tempRequired = requiredCols.has("tmin") || requiredCols.has("tmax");
  const activeDendroParams = {
    mcd: requiredCols.has("MCD"),
    tb: requiredCols.has("TasaBuenos"),
    ts: requiredCols.has("TasaSeveros"),
  };

  const [dendroFile, setDendroFile] = useState<SensorFileEntry>(emptyEntry);
  const [genericSensorFiles, setGenericSensorFiles] = useState<Record<string, SensorFileEntry>>({});
  const [tempFile, setTempFile] = useState<SensorFileEntry>(emptyEntry);
  const [fusionResult, setFusionResult] = useState<FusionResult | null>(null);

  const updateGenericFile = (featureName: string, update: Partial<SensorFileEntry>) => {
    setGenericSensorFiles((prev) => ({ ...prev, [featureName]: { ...(prev[featureName] ?? emptyEntry()), ...update } }));
  };

  const allSensorFilesReady = useMemo(() => {
    const dendroOk = !dendroRequired || Boolean(dendroFile.dataset && !dendroFile.dataset.errors.length && dendroFile.timestampCol && dendroFile.dataCol);
    const genericOk = genericSensors.every((s) => {
      const e = genericSensorFiles[s.featureName];
      return e?.dataset && !e.dataset.errors.length && e.timestampCol && e.dataCol;
    });
    const tempOk = !tempRequired || Boolean(tempFile.dataset && !tempFile.dataset.errors.length && tempFile.timestampCol && tempFile.dataCol);
    return dendroOk && genericOk && tempOk;
  }, [dendroRequired, dendroFile, genericSensors, genericSensorFiles, tempRequired, tempFile]);

  const extractedTelemetry = extractTelemetryMutation.data?.success ? extractTelemetryMutation.data : null;
  const extractedTelemetryErrors = useMemo(() => {
    if (extractTelemetryMutation.error instanceof Error) return [extractTelemetryMutation.error.message];
    if (extractTelemetryMutation.data && !extractTelemetryMutation.data.success) return extractTelemetryMutation.data.errors;
    return [];
  }, [extractTelemetryMutation.data, extractTelemetryMutation.error]);

  const telemetryReady = selectedTelemetry.length === 0 || Boolean(extractedTelemetry);
  const canExtractTelemetry = selectedTelemetry.length > 0 && Boolean(punto);
  const canFuse = allSensorFilesReady && telemetryReady;

  const recentHistory = historyQuery.data?.predictions ?? [];

  const predictedForDate = useMemo(() => {
    if (!fusionResult) return null;
    const range = fusionResult.sensorDateRange ?? getDateRangeFromRows(fusionResult.rows);
    return range ? addOneDay(range[1]) : null;
  }, [fusionResult]);

  const duplicateExists = useMemo(
    () => Boolean(predictedForDate && recentHistory.some((p) => p.predicted_for_date === predictedForDate)),
    [predictedForDate, recentHistory],
  );

  const canPredict = Boolean(
    fusionResult &&
    model &&
    fusionResult.rowCount >= model.window_size &&
    !predictMutation.isPending &&
    !duplicateExists,
  );

  const chartData = useMemo(() => {
    if (!recentHistory.length) return [];
    return [...recentHistory]
      .sort((a, b) => a.predicted_for_date.localeCompare(b.predicted_for_date))
      .map((p) => ({
        date: p.predicted_for_date,
        ...Object.fromEntries(Object.entries(p.predictions).map(([k, v]) => [k, Number(v.toFixed(4))])),
      }));
  }, [recentHistory]);

  const handleSensorFileUpload = async (sensorType: string, file: File) => {
    const setLoading = (loading: boolean) => {
      if (sensorType === "dendro") setDendroFile((e) => ({ ...e, isLoading: loading }));
      else if (sensorType === "temp") setTempFile((e) => ({ ...e, isLoading: loading }));
      else updateGenericFile(sensorType, { isLoading: loading });
    };
    setLoading(true);
    setFusionResult(null);
    try {
      const dataset = await parseCsvFileGeneric(file);
      const update: Partial<SensorFileEntry> = { dataset, isLoading: false, timestampCol: "", dataCol: "" };
      if (sensorType === "dendro") setDendroFile((e) => ({ ...e, ...update }));
      else if (sensorType === "temp") setTempFile((e) => ({ ...e, ...update }));
      else updateGenericFile(sensorType, update);
      toast.success("Archivo cargado", { description: `${file.name} procesado correctamente.` });
    } catch (err) {
      setLoading(false);
      toast.error("No se pudo procesar el archivo", { description: err instanceof Error ? err.message : "Error desconocido." });
    }
  };

  const buildSensorInputs = (): SensorFileInput[] => {
    const inputs: SensorFileInput[] = [];
    if (dendroRequired && dendroFile.dataset && dendroFile.timestampCol && dendroFile.dataCol) {
      const dendroCalc = calculateDendroParams(dendroFile.dataset.allRows, dendroFile.timestampCol, dendroFile.dataCol, activeDendroParams);
      dendroCalc.warnings.forEach((w) => toast.warning("Dendrómetro", { description: w }));
      for (const sensor of dendroSensors) {
        if (sensor.csvCol === "MCD" && dendroCalc.mcd) inputs.push({ canonicalCol: sensor.csvCol, precomputedDaily: dendroCalc.mcd, dataset: dendroFile.dataset, timestampCol: dendroFile.timestampCol, dataCol: dendroFile.dataCol });
        if (sensor.csvCol === "TasaBuenos" && dendroCalc.tb) inputs.push({ canonicalCol: sensor.csvCol, precomputedDaily: dendroCalc.tb, dataset: dendroFile.dataset, timestampCol: dendroFile.timestampCol, dataCol: dendroFile.dataCol });
        if (sensor.csvCol === "TasaSeveros" && dendroCalc.ts) inputs.push({ canonicalCol: sensor.csvCol, precomputedDaily: dendroCalc.ts, dataset: dendroFile.dataset, timestampCol: dendroFile.timestampCol, dataCol: dendroFile.dataCol });
      }
    }
    for (const sensor of genericSensors) {
      const e = genericSensorFiles[sensor.featureName];
      if (e?.dataset && e.timestampCol && e.dataCol) inputs.push({ canonicalCol: sensor.csvCol, dataset: e.dataset, timestampCol: e.timestampCol, dataCol: e.dataCol });
    }
    if (tempRequired && tempFile.dataset && tempFile.timestampCol && tempFile.dataCol) {
      if (requiredCols.has("tmin")) inputs.push({ canonicalCol: "tmin", dataset: tempFile.dataset, timestampCol: tempFile.timestampCol, dataCol: tempFile.dataCol, aggregation: "min" });
      if (requiredCols.has("tmax")) inputs.push({ canonicalCol: "tmax", dataset: tempFile.dataset, timestampCol: tempFile.timestampCol, dataCol: tempFile.dataCol, aggregation: "max" });
    }
    return inputs;
  };

  const handleExtractTelemetry = async () => {
    if (!model || !punto || selectedTelemetry.length === 0) return;
    const inputs = buildSensorInputs();
    const merged = inputs.length > 0 ? mergeSensorFiles(inputs) : null;
    const range = merged?.dateRange;
    if (!range) {
      toast.error("Carga primero sensores", { description: "Se necesita el rango temporal de los sensores para extraer telemetría." });
      return;
    }
    // Colchón hacia atrás: en ventanas cortas el rango del sensor puede no contener
    // ninguna pasada limpia de Sentinel-2 (revisita ~5 días + filtro de nubes).
    // Ampliamos solo el inicio; la fusión propaga (clamp forward) el último índice
    // observado hacia los días del sensor, sin añadir filas extra al CSV final.
    const TELEMETRY_LOOKBACK_DAYS = 15;
    const bufferedStart = new Date(range[0]);
    bufferedStart.setDate(bufferedStart.getDate() - TELEMETRY_LOOKBACK_DAYS);
    await extractTelemetryMutation.mutateAsync({
      features: [...new Set([...features, ...selectedTelemetry])],
      punto,
      startDate: bufferedStart.toISOString().slice(0, 10),
      endDate: range[1],
      cloudThreshold,
    });
  };

  const handleFuse = () => {
    if (!canFuse) return;
    const merged = mergeSensorFiles(buildSensorInputs());
    const telemetryPoints = extractedTelemetry ? extractedTelemetry.points : [];
    const result = fuseSensorAndTelemetry({
      sensorRows: merged.rows,
      sensorHeaders: merged.headers,
      telemetryPoints,
      selectedIndices: selectedTelemetry,
    });
    setFusionResult(result);
    toast.success("Fusión completada", { description: `${result.rowCount} filas listas para predicción.` });
  };

  const handlePredict = async () => {
    if (!modelId || !fusionResult || !canPredict) return;
    const csvContent = fusionResultToCsv(fusionResult, ";");
    const csvBlob = new Blob(["﻿" + csvContent], { type: "text/csv;charset=utf-8;" });
    try {
      await predictMutation.mutateAsync({ modelId, csvBlob });
      toast.success("Valor generado correctamente");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error desconocido.";
      if (msg.startsWith("409")) {
        toast.error("Predicción duplicada", { description: `Ya existe un valor generado para el ${predictedForDate ?? "esa fecha"}.` });
      } else {
        toast.error("Error al generar valor", { description: msg });
      }
    }
  };

  if (modelQuery.isLoading || featureModelQuery.isLoading) {
    return <div className="section-container py-10 text-sm text-muted-foreground">Cargando modelo…</div>;
  }

  if (!model || !featureModel) {
    return (
      <div className="section-container py-10">
        <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-5 text-destructive">No se pudo cargar el modelo.</div>
      </div>
    );
  }

  if (!punto) {
    return (
      <div className="section-container py-10">
        <Link to="/mis-modelos" className="mb-5 inline-flex items-center text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="mr-2 h-4 w-4" />Volver a mis modelos</Link>
        <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-5 text-destructive">
          <div className="flex gap-3"><AlertTriangle className="h-5 w-5" /><p>Este modelo no tiene ubicación guardada y no puede extraer telemetría GEE.</p></div>
        </div>
      </div>
    );
  }

  const lastPrediction = predictMutation.data;
  const targetKeys = model.targets;

  return (
    <div className="w-full px-[36px] sm:px-[44px] lg:px-[52px] xl:px-[60px] 2xl:px-[320px] py-10">
      <Link to="/mis-modelos" className="mb-5 inline-flex items-center text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="mr-2 h-4 w-4" />Volver a mis modelos</Link>

      <div className="mb-8">
        <h1 className="text-2xl font-serif font-semibold">Generar valor</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Modelo {model.model_id.slice(0, 8)} · {model.treatment} · {model.algorithm}. Carga al menos {model.window_size} días completos para cubrir la ventana temporal.
        </p>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {model.targets.map((t) => <span key={t} className="rounded-md border border-primary/40 bg-primary/10 px-2.5 py-1 font-semibold text-primary">{t}</span>)}
          {model.input_features.map((f) => <span key={f} className="rounded-md border border-border bg-card px-2.5 py-1 text-muted-foreground">{f}</span>)}
        </div>
      </div>

      <div className="space-y-8">
        <SensorLocationMap punto={punto} />

        <section className="config-block">
          <div className="mb-5 flex items-start gap-3">
            <div className="rounded-lg bg-primary/10 p-2 text-olive"><TreeDeciduous className="h-5 w-5" /></div>
            <div>
              <h2 className="text-lg font-semibold">1. Datos históricos de sensores</h2>
              <p className="text-sm text-muted-foreground">Sube los sensores necesarios para cubrir la ventana del modelo, incluyendo histórico de la variable objetivo.</p>
            </div>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {dendroRequired && (
              <SensorFileCard
                label={`Dendrómetro (${requiredTargetCols.join(", ")})`}
                icon={TreeDeciduous}
                required
                dataset={dendroFile.dataset}
                timestampCol={dendroFile.timestampCol}
                dataCol={dendroFile.dataCol}
                isLoading={dendroFile.isLoading}
                onUpload={(file) => void handleSensorFileUpload("dendro", file)}
                onClear={() => { setDendroFile(emptyEntry()); setFusionResult(null); }}
                onTimestampColChange={(col) => { setDendroFile((e) => ({ ...e, timestampCol: col })); setFusionResult(null); }}
                onDataColChange={(col) => { setDendroFile((e) => ({ ...e, dataCol: col })); setFusionResult(null); }}
              />
            )}
            {tempRequired && (
              <SensorFileCard
                label="Temperatura del aire"
                icon={Thermometer}
                required
                dataset={tempFile.dataset}
                timestampCol={tempFile.timestampCol}
                dataCol={tempFile.dataCol}
                isLoading={tempFile.isLoading}
                onUpload={(file) => void handleSensorFileUpload("temp", file)}
                onClear={() => { setTempFile(emptyEntry()); setFusionResult(null); }}
                onTimestampColChange={(col) => { setTempFile((e) => ({ ...e, timestampCol: col })); setFusionResult(null); }}
                onDataColChange={(col) => { setTempFile((e) => ({ ...e, dataCol: col })); setFusionResult(null); }}
              />
            )}
            {genericSensors.map((sensor) => {
              const entry = genericSensorFiles[sensor.featureName] ?? emptyEntry();
              return (
                <SensorFileCard
                  key={sensor.featureName}
                  label={sensor.label}
                  icon={TreeDeciduous}
                  required
                  dataset={entry.dataset}
                  timestampCol={entry.timestampCol}
                  dataCol={entry.dataCol}
                  isLoading={entry.isLoading}
                  onUpload={(file) => void handleSensorFileUpload(sensor.featureName, file)}
                  onClear={() => { updateGenericFile(sensor.featureName, emptyEntry()); setFusionResult(null); }}
                  onTimestampColChange={(col) => { updateGenericFile(sensor.featureName, { timestampCol: col }); setFusionResult(null); }}
                  onDataColChange={(col) => { updateGenericFile(sensor.featureName, { dataCol: col }); setFusionResult(null); }}
                />
              );
            })}
          </div>
        </section>

        <section className="config-block">
          <div className="mb-5 flex items-start gap-3">
            <div className="rounded-lg bg-primary/10 p-2 text-olive"><Satellite className="h-5 w-5" /></div>
            <div>
              <h2 className="text-lg font-semibold">2. Telemetría GEE</h2>
              <p className="text-sm text-muted-foreground">Se extraen los índices requeridos ({selectedTelemetry.join(", ") || "ninguno"}) usando la ubicación guardada en el modelo.</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={() => void handleExtractTelemetry()} disabled={!canExtractTelemetry || !allSensorFilesReady || extractTelemetryMutation.isPending}>
              {extractTelemetryMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
              Extraer telemetría
            </Button>
            {selectedTelemetry.length === 0 && <StatusTag tone="neutral">El modelo no usa telemetría</StatusTag>}
            {extractedTelemetry && <StatusTag tone="success">{`${extractedTelemetry.points.length} fechas extraídas`}</StatusTag>}
          </div>
          {extractedTelemetryErrors.length > 0 && (
            <div className="mt-4 rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">
              <ul className="list-disc space-y-1 pl-5">{extractedTelemetryErrors.map((e, i) => <li key={i}>{e}</li>)}</ul>
            </div>
          )}
          {extractedTelemetry && <TelemetryPreview extractedTelemetry={extractedTelemetry} />}
        </section>

        <section className="config-block">
          <div className="mb-5 flex items-start gap-3">
            <div className="rounded-lg bg-primary/10 p-2 text-olive"><GitMerge className="h-5 w-5" /></div>
            <div>
              <h2 className="text-lg font-semibold">3. Fusión y generación</h2>
              <p className="text-sm text-muted-foreground">Fusiona sensores y telemetría, y genera un único valor sin predicción recursiva.</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button onClick={handleFuse} disabled={!canFuse}><GitMerge className="mr-2 h-4 w-4" />Fusionar datos</Button>
            <Button onClick={() => void handlePredict()} disabled={!canPredict}>
              {predictMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
              Generar valor
            </Button>
          </div>
          {fusionResult && (
            <div className="mt-5 rounded-lg border border-border bg-muted/20 p-4 text-sm">
              <p>
                <strong>{fusionResult.rowCount}</strong> filas fusionadas. Rango: {getDateRangeFromRows(fusionResult.rows)?.join(" — ") ?? "—"}.
                {predictedForDate && (
                  <span className="ml-2 text-muted-foreground">→ predicción para <strong>{fmtDate(predictedForDate)}</strong></span>
                )}
              </p>
              {fusionResult.rowCount < model.window_size && <p className="mt-1 text-destructive">Se necesitan al menos {model.window_size} filas completas.</p>}
              {duplicateExists && predictedForDate && (
                <div className="mt-3 flex items-start gap-2 rounded-md border border-amber-400/40 bg-amber-400/10 p-3 text-amber-700 dark:text-amber-400">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <p>Ya existe una predicción para el {fmtDate(predictedForDate)}. Para generar un nuevo valor avanza los datos hasta una fecha posterior.</p>
                </div>
              )}
              {fusionResult.warnings.length > 0 && <ul className="mt-2 list-disc pl-5 text-satellite-amber">{fusionResult.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
            </div>
          )}
          {lastPrediction && (
            <div className="mt-5 rounded-xl border border-sensor-green/25 bg-sensor-green/10 p-5">
              <div className="mb-4 flex items-center gap-2 text-sensor-green"><CheckCircle2 className="h-5 w-5" /><p className="font-semibold">Valor generado para el {fmtDate(lastPrediction.predicted_for_date)}</p></div>
              <p className="mb-3 text-sm text-muted-foreground">Generado el {fmt(lastPrediction.generated_at)} con {lastPrediction.input_row_count} filas de entrada.</p>
              <div className="grid gap-3 sm:grid-cols-3">
                {Object.entries(lastPrediction.predictions).map(([target, value]) => (
                  <div key={target} className="rounded-lg border border-border bg-background/80 p-4">
                    <p className="text-sm text-muted-foreground">{target}</p>
                    <p className="mt-1 text-2xl font-semibold">{Number(value).toFixed(4)}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        <section className="config-block">
          <div className="mb-4 flex items-center gap-2">
            <History className="h-5 w-5 text-olive" />
            <h2 className="text-lg font-semibold">Trazabilidad de predicciones</h2>
          </div>

          {historyQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">Cargando historial…</p>
          ) : recentHistory.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aún no hay predicciones guardadas para este modelo.</p>
          ) : (
            <>
              <div className="mb-6 h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={fmtDate}
                      tick={{ fontSize: 11 }}
                      stroke="var(--muted-foreground)"
                    />
                    <YAxis tick={{ fontSize: 11 }} stroke="var(--muted-foreground)" width={60} />
                    <Tooltip
                      labelFormatter={(label) => `Fecha: ${fmtDate(String(label))}`}
                      formatter={(value, name) => [Number(value).toFixed(4), name]}
                      contentStyle={{ fontSize: 12 }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    {targetKeys.map((target, i) => (
                      <Line
                        key={target}
                        type="monotone"
                        dataKey={target}
                        stroke={CHART_COLORS[i % CHART_COLORS.length]}
                        strokeWidth={2}
                        dot={{ r: 3 }}
                        activeDot={{ r: 5 }}
                        connectNulls
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>

              <div className="space-y-2">
                {recentHistory.map((p) => (
                  <div key={p.prediction_id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-background/70 p-3 text-sm">
                    <div className="flex flex-col gap-0.5">
                      <span className="font-medium">{fmtDate(p.predicted_for_date)}</span>
                      <span className="text-xs text-muted-foreground">Generado el {fmt(p.generated_at)}</span>
                    </div>
                    <span className="text-muted-foreground">{Object.entries(p.predictions).map(([t, v]) => `${t}: ${Number(v).toFixed(4)}`).join(" · ")}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
