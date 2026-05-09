
import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import {
  AlertTriangle,
  Award,
  CheckCircle2,
  Database,
  Download,
  Droplets,
  FileDown,
  GitMerge,
  Info,
  Loader2,
  Play,
  Satellite,
  Sparkles,
  Thermometer,
  TreeDeciduous,
  Upload,
} from "lucide-react";

import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusTag, type StatusTone } from "@/components/ui/StatusTag";
import { CsvUploadSection } from "@/components/results/CsvUploadSection";
import { TelemetryPreview } from "@/components/results/TelemetryPreview";
import { SensorFileCard } from "@/components/config/SensorFileCard";
import { useExtractTelemetryMutation, useFeatureModelQuery } from "@/hooks/useConfiguratorApi";
import { useFeatureTrees } from "@/hooks/useFeatureTrees";
import { useGeo } from "@/hooks/useGeo";
import { useTrainModelMutation, useTrainingStatusQuery } from "@/hooks/useModelosApi";
import { modelosApi } from "@/services/modelosApi";
import {
  parseCsvFile,
  parseCsvFileGeneric,
  type CsvDataset,
  type GenericCsvDataset,
} from "@/lib/csvDataset";
import {
  csvRowsToTelemetryPoints,
  fuseSensorAndTelemetry,
  fusionResultToCsv,
  type FusionResult,
} from "@/lib/dataFusion";
import { mergeSensorFiles, type MergedSensorResult, type SensorFileInput } from "@/lib/sensorMerger";
import { calculateDendroParams } from "@/lib/dendroCalc";
import type { TargetMetrics } from "@/types/api";
import { getNode, getRelationChildren, buildCsvColumnInfo, buildTreatmentTrainingThresholds, collectCsvFeatures } from "@/utils/featureModel";

const TEMPERATURE_FEATURE_ID = "TemperaturaAire";

interface SensorFileEntry {
  dataset: GenericCsvDataset | null;
  timestampCol: string;
  dataCol: string;
  isLoading: boolean;
}

const emptyEntry = (): SensorFileEntry => ({ dataset: null, timestampCol: "", dataCol: "", isLoading: false });

function isoDateDaysAgo(days: number): string {
  const value = new Date();
  value.setDate(value.getDate() - days);
  return value.toISOString().slice(0, 10);
}

function isoDateToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function buildTelemetryWarnings(dataset: CsvDataset, selectedTelemetry: string[]): string[] {
  if (selectedTelemetry.length === 0) {
    return ["La configuración actual no activa telemetría; este CSV quedará como fuente opcional."];
  }
  const missing = selectedTelemetry.filter((idx) => !dataset.recognizedDataColumns.includes(idx));
  if (missing.length > 0) {
    return [`Índices seleccionados no encontrados en el CSV: ${missing.join(", ")}.`];
  }
  return [];
}

function getDatasetTone(dataset: CsvDataset | null, warnings: string[]): StatusTone {
  if (!dataset) return "neutral";
  if (dataset.errors.length > 0) return "warning";
  if (warnings.length > 0 || dataset.rowsWithMissingValues > 0) return "warning";
  return "success";
}

const DEFAULT_THRESHOLD = { minReject: 60, minWarn: 80, minGood: 365 };

type TrainingDataLevel = "reject" | "warn" | "acceptable" | "good";

function getTrainingDataLevel(rows: number, t: { minReject: number; minWarn: number; minGood: number }): TrainingDataLevel {
  if (rows < t.minReject) return "reject";
  if (rows < t.minWarn)   return "warn";
  if (rows < t.minGood)   return "acceptable";
  return "good";
}

function getCsvCols(node: { attributes?: Record<string, unknown> } | null): string[] {
  const attrs = node?.attributes ?? {};
  if (attrs.csv_col) return [String(attrs.csv_col)];
  if (attrs.csv_cols) return String(attrs.csv_cols).split(",").map((s) => s.trim()).filter(Boolean);
  return [];
}


export default function Results() {
  const featureModelQuery = useFeatureModelQuery();
  const { trees } = useFeatureTrees();
  const { geo } = useGeo();
  const extractTelemetryMutation = useExtractTelemetryMutation();
  const trainMutation = useTrainModelMutation();

  const features = trees[0]?.features ?? [];
  const model = featureModelQuery.data ?? null;

  // Derive config from features + model
  const tratamientoNode = model ? getNode(model, "Tratamiento") : null;
  const selectedTreatmentNode = tratamientoNode
    ? getRelationChildren(tratamientoNode).find((c) => features.includes(c.name))
    : null;
  const treatmentName = selectedTreatmentNode?.name ?? null;
  const treatmentLabel = (selectedTreatmentNode?.attributes?.label as string | undefined) ?? treatmentName ?? "No seleccionado";

  const sueloNode = model ? getNode(model, "TipoSuelo") : null;
  const selectedSueloNode = sueloNode
    ? getRelationChildren(sueloNode).find((c) => features.includes(c.name))
    : null;
  const sueloLabel = (selectedSueloNode?.attributes?.label as string | undefined) ?? selectedSueloNode?.name ?? "No seleccionado";

  const objetivoNode = model ? getNode(model, "VariableObjetivo") : null;
  const selectedObjetivoNode = objetivoNode
    ? getRelationChildren(objetivoNode).find((c) => features.includes(c.name))
    : null;
  const objetivoLabel = (selectedObjetivoNode?.attributes?.label as string | undefined) ?? selectedObjetivoNode?.name ?? "";

  const tempRequired = features.includes(TEMPERATURE_FEATURE_ID);

  const dendroSensors = useMemo(() => {
    const dendroNode = model ? getNode(model, "Dendrometro") : null;
    return dendroNode
      ? getRelationChildren(dendroNode)
          .map((node) => ({
            featureName: node.name,
            label: (node.attributes?.label as string | undefined) ?? node.name,
            csvCol: getCsvCols(node)[0] ?? node.name,
          }))
          .filter((sensor) => features.includes(sensor.featureName))
      : [];
  }, [model, features]);

  const dendroFeatureIds = useMemo(
    () => new Set([...dendroSensors.map((sensor) => sensor.featureName), TEMPERATURE_FEATURE_ID]),
    [dendroSensors],
  );

  const genericSensors = useMemo(
    () => model ? collectCsvFeatures(model, features, dendroFeatureIds) : [],
    [model, features, dendroFeatureIds],
  );

  const activeDendroParams = {
    mcd: dendroSensors.some((sensor) => sensor.csvCol === "MCD"),
    tb: dendroSensors.some((sensor) => sensor.csvCol === "TasaBuenos"),
    ts: dendroSensors.some((sensor) => sensor.csvCol === "TasaSeveros"),
  };

  const telemetryColumnInfo = useMemo(
    () => model ? buildCsvColumnInfo(model, "DatosTelemetria") : { aliases: {} as Record<string, string>, dataColumns: [] as string[] },
    [model],
  );
  const telemetryAliases = useMemo(
    () => ({ date: "date", ...telemetryColumnInfo.aliases }),
    [telemetryColumnInfo],
  );

  const treatmentThresholds = useMemo(
    () => (model ? buildTreatmentTrainingThresholds(model) : {}),
    [model],
  );
  const activeTreatmentThreshold = (treatmentName ? treatmentThresholds[treatmentName] : null) ?? DEFAULT_THRESHOLD;

  const selectedTelemetry = useMemo(() => {
    const telemetryNode = model ? getNode(model, "DatosTelemetria") : null;
    return telemetryNode
      ? getRelationChildren(telemetryNode)
          .filter((node) => features.includes(node.name) && getCsvCols(node).length > 0)
          .map((node) => node.name)
      : [];
  }, [model, features]);
  const selectedTelemetryColumns = useMemo(() => {
    const telemetryNode = model ? getNode(model, "DatosTelemetria") : null;
    return telemetryNode
      ? getRelationChildren(telemetryNode)
          .filter((node) => features.includes(node.name))
          .flatMap((node) => getCsvCols(node))
      : [];
  }, [model, features]);

  // Sensor files
  const [dendroFile, setDendroFile] = useState<SensorFileEntry>(emptyEntry);
  const [genericSensorFiles, setGenericSensorFiles] = useState<Record<string, SensorFileEntry>>({});
  const [tempFile, setTempFile] = useState<SensorFileEntry>(emptyEntry);
  const [mergedSensors, setMergedSensors] = useState<MergedSensorResult | null>(null);

  // Telemetry
  const [telemetryCsv, setTelemetryCsv] = useState<CsvDataset | null>(null);
  const [isLoadingTelemetryCsv, setIsLoadingTelemetryCsv] = useState(false);
  const [telemetryStartDate, setTelemetryStartDate] = useState(() => isoDateDaysAgo(90));
  const [telemetryEndDate, setTelemetryEndDate] = useState(() => isoDateToday());
  const [datesFromCsv, setDatesFromCsv] = useState(false);
  const [fusionResult, setFusionResult] = useState<FusionResult | null>(null);

  // Training
  const [activeModelId, setActiveModelId] = useState<string | null>(null);
  const trainingStatus = useTrainingStatusQuery(activeModelId);

  useEffect(() => { setActiveModelId(null); }, [fusionResult]);

  const updateGenericFile = (featureName: string, update: Partial<SensorFileEntry>) => {
    setGenericSensorFiles((prev) => ({ ...prev, [featureName]: { ...(prev[featureName] ?? emptyEntry()), ...update } }));
  };

  const selectedSensors = useMemo(() => {
    const items = genericSensors.map((s) => s.label);
    items.push(...dendroSensors.map((sensor) => sensor.label));
    if (tempRequired) {
      const tempNode = model ? getNode(model, TEMPERATURE_FEATURE_ID) : null;
      items.push((tempNode?.attributes?.label as string | undefined) ?? TEMPERATURE_FEATURE_ID);
    }
    return items;
  }, [genericSensors, dendroSensors, tempRequired, model]);

  const telemetryWarnings = useMemo(
    () => (telemetryCsv ? [...telemetryCsv.warnings, ...buildTelemetryWarnings(telemetryCsv, selectedTelemetryColumns)] : []),
    [telemetryCsv, selectedTelemetryColumns],
  );

  const allSensorFilesReady = useMemo(() => {
    const dendroOk = dendroSensors.length === 0 || Boolean(dendroFile.dataset && !dendroFile.dataset.errors.length && dendroFile.timestampCol && dendroFile.dataCol);
    const genericOk = genericSensors.every((s) => {
      const e = genericSensorFiles[s.featureName];
      return e?.dataset && !e.dataset.errors.length && e.timestampCol && e.dataCol;
    });
    const tempOk = !tempRequired || Boolean(tempFile.dataset && !tempFile.dataset.errors.length && tempFile.timestampCol && tempFile.dataCol);
    return dendroOk && genericOk && tempOk;
  }, [dendroFile, genericSensorFiles, tempFile, genericSensors, tempRequired, dendroSensors]);

  // Auto-sync date range from CSV files
  useEffect(() => {
    const inputs: SensorFileInput[] = [];
    if (dendroFile.dataset && dendroFile.timestampCol && dendroFile.dataCol) {
      const dendroCalc = calculateDendroParams(dendroFile.dataset.allRows, dendroFile.timestampCol, dendroFile.dataCol, activeDendroParams);
      for (const sensor of dendroSensors) {
        if (sensor.csvCol === "MCD" && dendroCalc.mcd) inputs.push({ canonicalCol: sensor.csvCol, precomputedDaily: dendroCalc.mcd, dataset: dendroFile.dataset, timestampCol: dendroFile.timestampCol, dataCol: dendroFile.dataCol });
        if (sensor.csvCol === "TasaBuenos" && dendroCalc.tb) inputs.push({ canonicalCol: sensor.csvCol, precomputedDaily: dendroCalc.tb, dataset: dendroFile.dataset, timestampCol: dendroFile.timestampCol, dataCol: dendroFile.dataCol });
        if (sensor.csvCol === "TasaSeveros" && dendroCalc.ts) inputs.push({ canonicalCol: sensor.csvCol, precomputedDaily: dendroCalc.ts, dataset: dendroFile.dataset, timestampCol: dendroFile.timestampCol, dataCol: dendroFile.dataCol });
      }
    }
    for (const sensor of genericSensors) {
      const e = genericSensorFiles[sensor.featureName];
      if (e?.dataset && e.timestampCol && e.dataCol) {
        inputs.push({ canonicalCol: sensor.csvCol, dataset: e.dataset, timestampCol: e.timestampCol, dataCol: e.dataCol });
      }
    }
    if (tempRequired && tempFile.dataset && tempFile.timestampCol && tempFile.dataCol) {
      inputs.push({ canonicalCol: "tmin", dataset: tempFile.dataset, timestampCol: tempFile.timestampCol, dataCol: tempFile.dataCol, aggregation: "min" });
      inputs.push({ canonicalCol: "tmax", dataset: tempFile.dataset, timestampCol: tempFile.timestampCol, dataCol: tempFile.dataCol, aggregation: "max" });
    }
    if (inputs.length === 0) { setDatesFromCsv(false); return; }
    const { dateRange } = mergeSensorFiles(inputs);
    if (dateRange) { setTelemetryStartDate(dateRange[0]); setTelemetryEndDate(dateRange[1]); setDatesFromCsv(true); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dendroFile, genericSensorFiles, tempFile, genericSensors, tempRequired, dendroSensors]);

  const extractedTelemetry = extractTelemetryMutation.data?.success ? extractTelemetryMutation.data : null;
  const extractedTelemetryErrors = useMemo(() => {
    if (extractTelemetryMutation.error instanceof Error) return [extractTelemetryMutation.error.message];
    if (extractTelemetryMutation.data && !extractTelemetryMutation.data.success) return extractTelemetryMutation.data.errors;
    return [];
  }, [extractTelemetryMutation.data, extractTelemetryMutation.error]);

  const canExtractTelemetry = !telemetryCsv && selectedTelemetry.length > 0 && Boolean(geo.punto);
  const telemetrySource = telemetryCsv && telemetryCsv.errors.length === 0 ? "csv" : extractedTelemetry ? "gee" : null;
  const canFuse = allSensorFilesReady && (selectedTelemetry.length === 0 || telemetrySource !== null);

  const fusedDataLevel = fusionResult ? getTrainingDataLevel(fusionResult.rowCount, activeTreatmentThreshold) : "reject";
  const isPollingTraining = trainingStatus.data?.status === "training";
  const canTrain = fusionResult !== null && fusedDataLevel !== "reject" && !trainMutation.isPending && !isPollingTraining && !activeModelId;

  const sensorFileErrors = useMemo(() => {
    const errors: string[] = [];
    if (dendroFile.dataset?.errors.length) errors.push(...dendroFile.dataset.errors.map((e) => `Dendrómetro: ${e}`));
    for (const sensor of genericSensors) {
      const e = genericSensorFiles[sensor.featureName];
      if (e?.dataset?.errors.length) errors.push(...e.dataset.errors.map((err) => `${sensor.label}: ${err}`));
    }
    if (tempRequired && tempFile.dataset?.errors.length) errors.push(...tempFile.dataset.errors.map((e) => `Temperatura: ${e}`));
    return errors;
  }, [dendroFile, genericSensorFiles, tempFile, genericSensors, tempRequired]);

  const qualitySummary = useMemo(() => {
    const totalSensorFiles = (dendroSensors.length > 0 ? 1 : 0) + genericSensors.length + (tempRequired ? 1 : 0);
    const loadedSensorFiles =
      (dendroSensors.length > 0 && dendroFile.dataset ? 1 : 0) +
      genericSensors.filter((s) => genericSensorFiles[s.featureName]?.dataset).length +
      (tempRequired && tempFile.dataset ? 1 : 0);
    const errors = [
      ...sensorFileErrors.map((e) => `Sensores: ${e}`),
      ...(telemetryCsv?.errors.map((e) => `Telemetría: ${e}`) ?? []),
      ...extractedTelemetryErrors.map((e) => `Extracción telemetría: ${e}`),
    ];
    const warnings = [
      ...(mergedSensors?.warnings.map((w) => `Sensores: ${w}`) ?? []),
      ...telemetryWarnings.map((w) => `Telemetría: ${w}`),
    ];
    const extractedTelemetryRows = !telemetryCsv && extractedTelemetry?.success ? extractedTelemetry.points.length : 0;
    const totalRows = (mergedSensors?.rowCount ?? 0) + (telemetryCsv?.rowCount ?? 0) + extractedTelemetryRows;

    let tone: StatusTone = "neutral";
    let title = "Preparado con datos predeterminados";
    let description = "No se ha cargado ningún archivo de sensor. El entrenamiento podrá continuar con las fuentes predeterminadas del sistema.";

    if (loadedSensorFiles > 0 || extractedTelemetryRows > 0 || errors.length > 0) {
      if (errors.length > 0) {
        tone = "warning"; title = "Revisión necesaria antes del entrenamiento";
        description = "Hay incidencias en los datos externos. Si se mantienen, esa fuente podrá sustituirse por datos predeterminados.";
      } else if (warnings.length > 0) {
        tone = "warning"; title = "Calidad revisada con curación prevista";
        description = "Se detectan huecos o avisos en los datos. La estrategia de curación quedará informada antes del entrenamiento.";
      } else {
        tone = "success";
        title = extractedTelemetryRows > 0 && loadedSensorFiles === 0 ? "Extracción de telemetría lista para revisión" : "Datos externos listos para el siguiente paso";
        description = extractedTelemetryRows > 0 && loadedSensorFiles === 0 ? "La extracción remota se ha visualizado correctamente." : "La estructura de los datos externos es válida.";
      }
    }

    const sensorsSource =
      loadedSensorFiles === 0 ? "Datos predeterminados"
      : !allSensorFilesReady ? `${loadedSensorFiles}/${totalSensorFiles} archivos cargados (faltan columnas o archivos)`
      : mergedSensors ? `${mergedSensors.rowCount} filas fusionadas de ${loadedSensorFiles} sensor(es)`
      : `${loadedSensorFiles}/${totalSensorFiles} archivos listos para fusionar`;

    const telemetrySourceLabel = telemetryCsv
      ? telemetryCsv.errors.length > 0 ? "CSV con incidencias; fallback a datos predeterminados" : `CSV cargado (${telemetryCsv.fileName})`
      : extractedTelemetryErrors.length > 0 ? "Extracción Earth Engine con incidencias; fallback a datos predeterminados"
      : extractedTelemetry?.success ? `Extracción Earth Engine visualizada (${extractedTelemetry.points.length} fechas)`
      : "Datos predeterminados / extracción Earth Engine disponible";

    return { tone, title, description, errors, warnings, totalRows, sensorsSource, telemetrySource: telemetrySourceLabel };
  }, [genericSensors, genericSensorFiles, tempRequired, dendroFile, tempFile, sensorFileErrors, telemetryCsv, extractedTelemetryErrors, mergedSensors, telemetryWarnings, extractedTelemetry, allSensorFilesReady, dendroSensors]);

  const handleSensorFileUpload = async (sensorType: string, file: File) => {
    const setLoading = (loading: boolean) => {
      if (sensorType === "dendro") setDendroFile((e) => ({ ...e, isLoading: loading }));
      else if (sensorType === "temp") setTempFile((e) => ({ ...e, isLoading: loading }));
      else updateGenericFile(sensorType, { isLoading: loading });
    };
    setLoading(true); setMergedSensors(null); setFusionResult(null);
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

  const handleTelemetryCsvUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setIsLoadingTelemetryCsv(true);
    try {
      const dataset = await parseCsvFile(file, "telemetry", telemetryAliases, telemetryColumnInfo.dataColumns, ["date"]);
      setTelemetryCsv(dataset); extractTelemetryMutation.reset(); setFusionResult(null);
      toast.success("CSV de telemetría cargado", { description: `Archivo procesado: ${file.name}` });
    } catch (error) {
      setTelemetryCsv(null);
      toast.error("No se pudo procesar el CSV", { description: error instanceof Error ? error.message : "Error desconocido." });
    } finally { setIsLoadingTelemetryCsv(false); event.target.value = ""; }
  };

  const handleExtractTelemetry = async () => {
    if (!canExtractTelemetry) return;
    await extractTelemetryMutation.mutateAsync({
      features,
      punto: geo.punto,
      startDate: telemetryStartDate,
      endDate: telemetryEndDate,
      cloudThreshold: geo.cloudThreshold,
    });
  };

  const handleFuse = () => {
    if (!canFuse) return;
    const inputs: SensorFileInput[] = [];
    if (dendroFile.dataset && dendroFile.timestampCol && dendroFile.dataCol) {
      const dendroCalc = calculateDendroParams(dendroFile.dataset.allRows, dendroFile.timestampCol, dendroFile.dataCol, activeDendroParams);
      if (dendroCalc.warnings.length > 0) dendroCalc.warnings.forEach((w) => toast.warning("Dendrómetro", { description: w }));
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
      inputs.push({ canonicalCol: "tmin", dataset: tempFile.dataset, timestampCol: tempFile.timestampCol, dataCol: tempFile.dataCol, aggregation: "min" });
      inputs.push({ canonicalCol: "tmax", dataset: tempFile.dataset, timestampCol: tempFile.timestampCol, dataCol: tempFile.dataCol, aggregation: "max" });
    }
    const merged = mergeSensorFiles(inputs);
    setMergedSensors(merged);
    if (merged.dateRange) { setTelemetryStartDate(merged.dateRange[0]); setTelemetryEndDate(merged.dateRange[1]); }

    const telemetryPoints = selectedTelemetry.length === 0
      ? []
      : telemetrySource === "gee" && extractedTelemetry
        ? extractedTelemetry.points
        : csvRowsToTelemetryPoints(telemetryCsv!.allRows, telemetryCsv!.headers, selectedTelemetryColumns);
    const activeIndices = telemetrySource === "gee" && extractedTelemetry
      ? extractedTelemetry.indices
      : selectedTelemetry.length === 0
        ? []
        : telemetryCsv!.recognizedDataColumns.filter((col) => selectedTelemetryColumns.includes(col));

    const result = fuseSensorAndTelemetry({
      sensorRows: merged.rows, sensorHeaders: merged.headers,
      telemetryPoints, selectedIndices: activeIndices.length > 0 ? activeIndices : [...selectedTelemetry],
    });
    setFusionResult(result);
    toast.success("Fusión completada", { description: `${result.rowCount} filas · ${result.exactMatchCount} exactas · ${result.interpolatedCount} interpoladas/clampeadas` });
  };

  const handleExport = () => {
    const payload = JSON.stringify({ version: 1, features, geo }, null, 2);
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `config-${geo.nombre || "parcela"}-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
  };

  const handleDownloadFusion = () => {
    if (!fusionResult) return;
    const csv = fusionResultToCsv(fusionResult, ";");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "datos_fusionados.csv";
    document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
  };

  const handleGenerateSensor = async () => {
    if (!fusionResult || !canTrain) return;
    const csvContent = fusionResultToCsv(fusionResult, ";");
    const csvBlob = new Blob(["﻿" + csvContent], { type: "text/csv;charset=utf-8;" });
    try {
      const result = await trainMutation.mutateAsync({ features, csvBlob, geo });
      setActiveModelId(result.model_id);
      toast.success("Entrenamiento iniciado", { description: `Modelo ${result.model_id.slice(0, 8)}… en proceso.` });
    } catch (err) {
      toast.error("Error al iniciar el entrenamiento", { description: err instanceof Error ? err.message : "Error desconocido." });
    }
  };

  if (!selectedObjetivoNode) {
    return (
      <div className="section-container py-10">
        <div className="mx-auto max-w-3xl rounded-xl border border-destructive/20 bg-destructive/10 p-5 text-destructive">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5" />
            <div>
              <p className="font-medium">No hay una variable objetivo seleccionada.</p>
              <p className="mt-1 text-sm">Vuelve al configurador y completa todos los pasos antes de acceder a esta página.</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="section-container max-w-7xl py-10">
      <div className="mx-auto max-w-6xl space-y-6">
        <div>
          <h1 className="animate-reveal-up mb-2 text-3xl font-bold">Validación del modelo y datos de entrenamiento</h1>
          <p className="animate-reveal-up text-muted-foreground" style={{ animationDelay: "60ms" }}>
            Revisa la configuración seleccionada, añade tus CSV de sensores y telemetría, y deja preparado el paso previo a generar el sensor digital.
          </p>
        </div>

        {/* 1. Resumen */}
        <section className="config-block animate-reveal-up" style={{ animationDelay: "100ms" }}>
          <div className="mb-5 flex items-start justify-between gap-3">
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-primary/10 p-2 text-olive"><CheckCircle2 className="h-5 w-5" /></div>
              <div>
                <h2 className="text-lg font-semibold">1. Resumen de la configuración</h2>
                <p className="text-sm text-muted-foreground">Comprueba que la configuración es correcta antes de continuar.</p>
              </div>
            </div>
            <Button variant="outline" size="sm" className="shrink-0" onClick={handleExport}>
              <Download className="mr-2 h-4 w-4" />Exportar configuración
            </Button>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {/* Parcela */}
            <div className="rounded-xl border border-border bg-muted/20 p-4 space-y-3">
              <p className="text-[0.65rem] font-bold uppercase tracking-widest text-muted-foreground">Parcela</p>
              <div className="space-y-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Nombre</span>
                  <p className="font-medium">{geo.nombre || <span className="text-muted-foreground italic">Sin nombre</span>}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Localización</span>
                  <p className="font-medium">
                    {geo.provinciaNombre && geo.municipioNombre
                      ? `${geo.municipioNombre}, ${geo.provinciaNombre}`
                      : geo.provinciaNombre ?? <span className="text-muted-foreground italic">No especificada</span>}
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Geometría</span>
                  <p className="font-medium">
                    {geo.punto
                      ? <span className="text-sensor-green">Definida</span>
                      : <span className="text-satellite-amber">Sin geometría</span>}
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Tratamiento</span>
                  <p className="font-medium">{treatmentLabel}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Tipo de suelo</span>
                  <p className="font-medium">{sueloLabel}</p>
                </div>
              </div>
            </div>

            {/* Configuración del modelo */}
            <div className="rounded-xl border border-border bg-muted/20 p-4 space-y-3 flex flex-col">
              <p className="text-[0.65rem] font-bold uppercase tracking-widest text-muted-foreground">Configuración del modelo</p>
              <div className="space-y-3 text-sm flex-1">
                <div>
                  <span className="text-muted-foreground">Entradas</span>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {[...selectedSensors, ...selectedTelemetry].length > 0
                      ? [...selectedSensors, ...selectedTelemetry].map((s) => (
                          <span key={s} className="inline-flex items-center rounded-md border border-border bg-card px-2 py-0.5 text-xs font-medium">{s}</span>
                        ))
                      : <span className="text-xs text-muted-foreground italic">Ninguna entrada seleccionada</span>}
                  </div>
                </div>
                <div>
                  <span className="text-muted-foreground">Salida</span>
                  <div className="mt-1">
                    <span className="inline-flex items-center rounded-md border border-primary/40 bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
                      {objetivoLabel}
                    </span>
                  </div>
                </div>
              </div>
              {(() => {
                const targetAlgo = selectedObjetivoNode?.attributes?.preferred_algorithm as string | undefined;
                const treatmentAlgo = selectedTreatmentNode?.attributes?.preferred_algorithm as string | undefined;
                const algo = targetAlgo ?? treatmentAlgo;
                if (!algo) return null;
                const targetWindow = selectedObjetivoNode?.attributes?.window_size_override;
                const treatmentWindow = selectedTreatmentNode?.attributes?.window_size;
                const window = targetWindow ?? treatmentWindow;
                return (
                  <div className="border-t border-border/60 pt-3 text-sm">
                    <span className="text-muted-foreground">Algoritmo preferido</span>
                    <p className="mt-0.5 font-medium">
                      {String(algo)}
                      {window && (
                        <span className="ml-1.5 font-normal text-muted-foreground">· ventana {String(window)} días</span>
                      )}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Algoritmo asociado al objetivo. Si LSTM no es viable (TensorFlow ausente o datos insuficientes) el sistema empleará RandomForest automáticamente.
                    </p>
                  </div>
                );
              })()}
            </div>
          </div>
        </section>

        {/* 2. Ingesta de datos */}
        <section className="config-block animate-reveal-up" style={{ animationDelay: "140ms" }}>
          <div className="mb-5 flex items-start gap-3">
            <div className="rounded-lg bg-primary/10 p-2 text-olive"><Upload className="h-5 w-5" /></div>
            <div>
              <h2 className="text-lg font-semibold">2. Ingesta de datos</h2>
              <p className="text-sm text-muted-foreground">Sube un CSV por sensor. El sistema los unifica a resolución diaria antes de fusionarlos con telemetría.</p>
            </div>
          </div>
          <div className="space-y-4">
            {/* Sensor files */}
            <div className="rounded-xl border border-border bg-background/70 p-5">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 rounded-lg bg-primary/10 p-2 text-olive"><Droplets className="h-5 w-5" /></div>
                  <div>
                    <h3 className="text-lg font-semibold">Datos de sensores</h3>
                    <p className="text-sm text-muted-foreground">Un archivo CSV por sensor. Elige la columna de fecha/hora y la columna con el dato medido.</p>
                  </div>
                </div>
                <StatusTag tone={allSensorFilesReady ? "success" : dendroFile.dataset ? "warning" : "neutral"}>
                  {allSensorFilesReady ? "Listos" : dendroFile.dataset ? "Incompleto" : "Opcional"}
                </StatusTag>
              </div>
              <div className="space-y-3">
                <SensorFileCard
                  label="Dendrómetro" icon={TreeDeciduous} required={true}
                  dataset={dendroFile.dataset} timestampCol={dendroFile.timestampCol} dataCol={dendroFile.dataCol} isLoading={dendroFile.isLoading}
                  onUpload={(file) => void handleSensorFileUpload("dendro", file)}
                  onClear={() => { setDendroFile(emptyEntry()); setMergedSensors(null); setFusionResult(null); }}
                  onTimestampColChange={(col) => setDendroFile((e) => ({ ...e, timestampCol: col }))}
                  onDataColChange={(col) => setDendroFile((e) => ({ ...e, dataCol: col }))}
                />
                {genericSensors.map((sensor) => {
                  const entry = genericSensorFiles[sensor.featureName] ?? emptyEntry();
                  return (
                    <SensorFileCard
                      key={sensor.featureName} label={sensor.label} icon={Droplets} required={true}
                      dataset={entry.dataset} timestampCol={entry.timestampCol} dataCol={entry.dataCol} isLoading={entry.isLoading}
                      onUpload={(file) => void handleSensorFileUpload(sensor.featureName, file)}
                      onClear={() => { setGenericSensorFiles((prev) => ({ ...prev, [sensor.featureName]: emptyEntry() })); setMergedSensors(null); setFusionResult(null); }}
                      onTimestampColChange={(col) => updateGenericFile(sensor.featureName, { timestampCol: col })}
                      onDataColChange={(col) => updateGenericFile(sensor.featureName, { dataCol: col })}
                    />
                  );
                })}
                {tempRequired && (
                  <SensorFileCard
                    label="Temperatura aire" icon={Thermometer} required={true}
                    dataset={tempFile.dataset} timestampCol={tempFile.timestampCol} dataCol={tempFile.dataCol} isLoading={tempFile.isLoading}
                    onUpload={(file) => void handleSensorFileUpload("temp", file)}
                    onClear={() => { setTempFile(emptyEntry()); setMergedSensors(null); setFusionResult(null); }}
                    onTimestampColChange={(col) => setTempFile((e) => ({ ...e, timestampCol: col }))}
                    onDataColChange={(col) => setTempFile((e) => ({ ...e, dataCol: col }))}
                  />
                )}
              </div>
            </div>

            {/* Telemetry */}
            <div className="rounded-xl border border-border bg-background/70 p-5">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 rounded-lg bg-primary/10 p-2 text-olive"><Satellite className="h-5 w-5" /></div>
                  <div>
                    <h3 className="text-lg font-semibold">Datos de telemetría</h3>
                    <p className="text-sm text-muted-foreground">Puedes calcular la telemetría con la integración existente o subir un CSV propio para sustituir esa fuente.</p>
                  </div>
                </div>
                <StatusTag tone={telemetryCsv ? "success" : extractedTelemetry ? "success" : "neutral"}>
                  {telemetryCsv ? "CSV propio activo" : extractedTelemetry ? "Extracción visualizada" : "Opcional"}
                </StatusTag>
              </div>
              <div className="space-y-4">
                <div className="rounded-lg border border-border bg-muted/20 p-4">
                  <div className="mb-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                      <p className="font-medium">Usar archivo propio</p>
                      <p className="text-sm text-muted-foreground">Si subes un CSV propio, se desactiva la visualización de telemetría calculada.</p>
                    </div>
                    {telemetryCsv && (
                      <Button type="button" variant="outline" size="sm" onClick={() => { setTelemetryCsv(null); setFusionResult(null); }}>
                        Volver a extracción remota
                      </Button>
                    )}
                  </div>
                  {isLoadingTelemetryCsv && <StatusTag tone="neutral">Procesando CSV de telemetría...</StatusTag>}
                  <div className="mt-3">
                    <Label htmlFor="telemetry-csv-upload" className="mb-2 block">Subir archivo CSV propio</Label>
                    <Input id="telemetry-csv-upload" type="file" accept=".csv,text/csv" onChange={(e) => void handleTelemetryCsvUpload(e)} />
                  </div>
                </div>
                {telemetryCsv ? (
                  <CsvUploadSection
                    title="CSV propio de telemetría" description="Este archivo sustituye la visualización de telemetría calculada."
                    kind="telemetry" icon={Satellite} expectedColumns={telemetryColumnInfo.dataColumns}
                    dataset={telemetryCsv} warnings={telemetryWarnings}
                    onUpload={(e) => void handleTelemetryCsvUpload(e)}
                    onClear={() => { setTelemetryCsv(null); setFusionResult(null); }} showUploadControls={false}
                  />
                ) : (
                  <div className="rounded-lg border border-border bg-muted/20 p-4">
                    <div className="mb-4">
                      <p className="font-medium">Extracción de telemetría</p>
                      <p className="text-sm text-muted-foreground">Configura el rango temporal para calcular y visualizar la serie de telemetría.</p>
                      {datesFromCsv && (
                        <div className="mt-1 flex items-center gap-1.5 text-sm text-blue-600 dark:text-blue-400">
                          <Info className="h-3.5 w-3.5 shrink-0" />
                          <span>Fechas ajustadas automáticamente según los CSVs cargados.</span>
                        </div>
                      )}
                    </div>
                    <div className="grid gap-4 md:grid-cols-3">
                      <div className="space-y-2">
                        <Label htmlFor="telemetry-start-date">Fecha inicio</Label>
                        <Input id="telemetry-start-date" type="date" value={telemetryStartDate} onChange={(e) => { setTelemetryStartDate(e.target.value); setDatesFromCsv(false); }} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="telemetry-end-date">Fecha fin</Label>
                        <Input id="telemetry-end-date" type="date" value={telemetryEndDate} onChange={(e) => { setTelemetryEndDate(e.target.value); setDatesFromCsv(false); }} />
                      </div>
                      <div className="flex items-end">
                        <Button onClick={() => void handleExtractTelemetry()} disabled={!canExtractTelemetry || extractTelemetryMutation.isPending} className="w-full">
                          {extractTelemetryMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                          Calcular datos
                        </Button>
                      </div>
                    </div>
                    {!canExtractTelemetry && (
                      <p className="mt-3 text-sm text-muted-foreground">Para calcular la telemetría necesitas una geometría de parcela y al menos un índice seleccionado.</p>
                    )}
                    {extractedTelemetryErrors.length > 0 && (
                      <div className="mt-4 rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">
                        <ul className="list-disc space-y-1 pl-5">{extractedTelemetryErrors.map((e, i) => <li key={i}>{e}</li>)}</ul>
                      </div>
                    )}
                    {extractedTelemetry?.success && <TelemetryPreview extractedTelemetry={extractedTelemetry} />}
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>

        {/* 3. Fusión */}
        {canFuse && (
          <section className="config-block animate-reveal-up" style={{ animationDelay: "165ms" }}>
            <div className="mb-5 flex items-start gap-3">
              <div className="rounded-lg bg-primary/10 p-2 text-olive"><GitMerge className="h-5 w-5" /></div>
              <div>
                <h2 className="text-lg font-semibold">3. Fusión de datos</h2>
                <p className="text-sm text-muted-foreground">Unifica los archivos de sensores a resolución diaria y combínalos con telemetría alineando por fecha.</p>
              </div>
            </div>
            <div className="mb-4 rounded-lg border border-border bg-muted/20 p-4 text-sm text-muted-foreground">
              <div className="flex items-start gap-2">
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-olive" />
                {mergedSensors?.dateRange ? (
                  <p>Rango de datos de sensores: <span className="font-medium text-foreground">{mergedSensors.dateRange[0]}</span> — <span className="font-medium text-foreground">{mergedSensors.dateRange[1]}</span>. Se añadirán las columnas de telemetría ({selectedTelemetry.join(", ")}, cloudCover).</p>
                ) : (
                  <p>Todos los archivos de sensor están listos. Se unificarán a resolución diaria y se fusionarán con las columnas de telemetría ({selectedTelemetry.join(", ")}, cloudCover).</p>
                )}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={handleFuse}><GitMerge className="mr-2 h-4 w-4" />Fusionar datos</Button>
              {fusionResult && (
                <Button variant="outline" onClick={handleDownloadFusion}><FileDown className="mr-2 h-4 w-4" />Descargar CSV fusionado</Button>
              )}
            </div>
            {fusionResult && (
              <div className="mt-5 space-y-4">
                <div className="grid gap-3 text-sm sm:grid-cols-4">
                  <div className="rounded-lg border border-border bg-muted/20 p-3"><p className="text-muted-foreground">Total filas</p><p className="mt-1 font-medium">{fusionResult.rowCount}</p></div>
                  <div className="rounded-lg border border-border bg-muted/20 p-3"><p className="text-muted-foreground">Coincidencia exacta</p><p className="mt-1 font-medium">{fusionResult.exactMatchCount}</p></div>
                  <div className="rounded-lg border border-border bg-muted/20 p-3"><p className="text-muted-foreground">Interpoladas / clampeadas</p><p className="mt-1 font-medium">{fusionResult.interpolatedCount}</p></div>
                </div>
                {(() => {
                  const t = activeTreatmentThreshold;
                  if (fusedDataLevel === "reject") return (
                    <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
                      <p className="font-semibold">Datos insuficientes para entrenar</p>
                      <p className="mt-1">El CSV fusionado tiene <strong>{fusionResult.rowCount} filas</strong>, por debajo del mínimo de <strong>{t.minReject}</strong>. Añade más datos históricos antes de continuar.</p>
                    </div>
                  );
                  if (fusedDataLevel === "warn") return (
                    <div className="rounded-lg border border-satellite-amber/30 bg-satellite-amber/10 p-4 text-sm text-satellite-amber">
                      <p className="font-semibold">Datos limitados — calidad del modelo reducida</p>
                      <p className="mt-1">Con <strong>{fusionResult.rowCount} filas</strong> el modelo puede entrenarse, pero los resultados serán poco fiables. Se usará RandomForest automáticamente (LSTM requiere al menos <strong>{t.minWarn}</strong> filas). Para resultados sólidos se recomiendan <strong>{t.minGood}+</strong> filas.</p>
                    </div>
                  );
                  if (fusedDataLevel === "acceptable") return (
                    <div className="rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground">
                      <p className="font-semibold text-foreground">Datos aceptables</p>
                      <p className="mt-1"><strong>{fusionResult.rowCount} filas</strong> son suficientes para entrenar. Para métricas óptimas se recomiendan <strong>{t.minGood}+</strong> filas.</p>
                    </div>
                  );
                  return null;
                })()}
                {fusionResult.warnings.length > 0 && (
                  <div className="rounded-lg border border-satellite-amber/20 bg-satellite-amber/10 p-4 text-sm text-satellite-amber">
                    <ul className="list-disc space-y-1 pl-5">{fusionResult.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
                  </div>
                )}
                <div>
                  <p className="mb-2 text-sm font-medium">Vista previa del CSV fusionado</p>
                  <div className="overflow-x-auto rounded-lg border border-border">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-muted/40">
                        <tr>{fusionResult.headers.filter((h) => !h.startsWith("_")).map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
                      </thead>
                      <tbody>
                        {fusionResult.rows.slice(0, 5).map((row, i) => (
                          <tr key={i} className={`border-t border-border ${row._telemetryInterpolated ? "bg-satellite-amber/5" : ""}`}>
                            {fusionResult.headers.filter((h) => !h.startsWith("_")).map((h) => (
                              <td key={h} className="px-3 py-2 align-top">
                                {row[h] !== null && row[h] !== undefined && row[h] !== "" ? String(row[h]) : <span className="text-muted-foreground">-</span>}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">Se muestran las primeras {Math.min(5, fusionResult.rowCount)} filas de {fusionResult.rowCount}.{fusionResult.interpolatedCount > 0 && " Filas con fondo amarillo tienen telemetría interpolada."}</p>
                  <p className="mt-2 text-xs text-muted-foreground">Si las primeras líneas de TasaBuenos o TasaSeveros se muestran como '-' es porque se calculan a partir de la MCD y necesitan datos de una semana completa.</p>
                </div>
              </div>
            )}
          </section>
        )}

        {/* 4. Calidad */}
        <section className="config-block animate-reveal-up" style={{ animationDelay: "200ms" }}>
          <div className="mb-5 flex items-start gap-3">
            <div className="rounded-lg bg-primary/10 p-2 text-olive"><Database className="h-5 w-5" /></div>
            <div>
              <h2 className="text-lg font-semibold">4. Calidad de datos y curación prevista</h2>
              <p className="text-sm text-muted-foreground">Este bloque deja preparada la comunicación de calidad antes del entrenamiento.</p>
            </div>
          </div>
          <div className={`mb-4 rounded-xl border p-4 ${qualitySummary.tone === "success" ? "border-sensor-green/20 bg-sensor-green/10" : qualitySummary.tone === "warning" ? "border-satellite-amber/20 bg-satellite-amber/10" : "border-border bg-muted/20"}`}>
            <div className="mb-2 flex items-center gap-2"><StatusTag tone={qualitySummary.tone}>{qualitySummary.title}</StatusTag></div>
            <p className="text-sm text-muted-foreground">{qualitySummary.description}</p>
          </div>
          <div className="grid gap-4 text-sm md:grid-cols-3">
            <div className="rounded-lg border border-border bg-muted/20 p-4"><p className="text-muted-foreground">Fuente prevista · sensores</p><p className="mt-1 font-medium">{qualitySummary.sensorsSource}</p></div>
            <div className="rounded-lg border border-border bg-muted/20 p-4"><p className="text-muted-foreground">Fuente prevista · telemetría</p><p className="mt-1 font-medium">{qualitySummary.telemetrySource}</p></div>
            <div className="rounded-lg border border-border bg-muted/20 p-4"><p className="text-muted-foreground">Indicadores detectados</p><p className="mt-1 font-medium">{qualitySummary.totalRows > 0 ? `${qualitySummary.totalRows} filas revisadas` : "Sin archivos cargados; se usarán datos predeterminados"}</p></div>
          </div>
          <div className="mt-4 rounded-lg border border-border bg-background/70 p-4 text-sm">
            <p className="font-medium">Estrategia de curación prevista</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
              <li>Si aparecen faltas o huecos en variables de suelo, se plantea interpolación lineal.</li>
              <li>Si faltan observaciones para indicadores de planta (MCD/TCT), se plantea ampliar la ventana semanal.</li>
              <li>Las reglas detalladas por tipo de suelo, parcela u otras condiciones siguen pendientes de definición.</li>
              <li>Si no se carga ningún archivo o alguna fuente no queda lista, el flujo podrá continuar con los datos predeterminados.</li>
            </ul>
          </div>
        </section>

        {/* 5. Entrenamiento */}
        <section className="config-block animate-reveal-up" style={{ animationDelay: "220ms" }}>
          <div className="mb-5 flex items-start gap-3">
            <div className="rounded-lg bg-primary/10 p-2 text-olive"><Award className="h-5 w-5" /></div>
            <div>
              <h2 className="text-lg font-semibold">5. Generación del sensor predictivo</h2>
              <p className="text-sm text-muted-foreground">Lanza el entrenamiento del modelo con los datos fusionados. El proceso puede tardar varios minutos.</p>
            </div>
          </div>
          {!activeModelId && !trainMutation.isPending && (
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <p className="text-sm text-muted-foreground">
                {!fusionResult ? "Primero fusiona los datos de sensores y telemetría en la sección 3."
                  : fusedDataLevel === "reject" ? "Los datos fusionados no alcanzan el mínimo necesario para entrenar."
                  : "El CSV fusionado está listo. Pulsa el botón para iniciar el entrenamiento."}
              </p>
              <Button onClick={() => void handleGenerateSensor()} disabled={!canTrain} className="shrink-0 transition-transform active:scale-[0.97]">
                <Sparkles className="mr-2 h-4 w-4" />Generar sensor
              </Button>
            </div>
          )}
          {trainMutation.isPending && !activeModelId && (
            <div className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /><span className="text-sm">Enviando datos al servidor…</span></div>
          )}
          {activeModelId && !trainingStatus.data && trainingStatus.isLoading && (
            <div className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /><span className="text-sm">Conectando con el proceso de entrenamiento…</span></div>
          )}
          {activeModelId && trainingStatus.data?.status === "training" && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Loader2 className="h-5 w-5 animate-spin text-olive" /><p className="font-medium">Entrenando modelo…</p>
                {trainingStatus.data.algorithm && <span className="rounded-full bg-olive/15 px-2 py-0.5 text-xs font-semibold text-olive">{trainingStatus.data.algorithm}</span>}
              </div>
              {trainingStatus.data.phase && <p className="text-sm text-muted-foreground">Fase: <span className="font-medium text-foreground">{trainingStatus.data.phase}</span></p>}
              {trainingStatus.data.current_target && <p className="text-sm text-muted-foreground">Objetivo: <span className="font-medium text-foreground">{trainingStatus.data.current_target}</span></p>}
              {trainingStatus.data.current_epoch != null && trainingStatus.data.total_epochs != null && (
                <div>
                  <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                    <span>Época {trainingStatus.data.current_epoch} / {trainingStatus.data.total_epochs}</span>
                    {trainingStatus.data.val_loss != null && <span>val_loss: {trainingStatus.data.val_loss.toFixed(4)}</span>}
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                    <div className="h-full bg-olive transition-all duration-500" style={{ width: `${Math.round((trainingStatus.data.current_epoch / trainingStatus.data.total_epochs) * 100)}%` }} />
                  </div>
                </div>
              )}
              {trainingStatus.data.n_train != null && <p className="text-xs text-muted-foreground">{trainingStatus.data.n_train} muestras de entrenamiento{trainingStatus.data.n_val != null ? ` · ${trainingStatus.data.n_val} de validación` : ""}</p>}
              <p className="text-xs text-muted-foreground">ID: {activeModelId}</p>
            </div>
          )}
          {activeModelId && trainingStatus.data?.status === "error" && (
            <div className="space-y-4">
              <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">
                <p className="font-semibold">Error en el entrenamiento</p>
                {trainingStatus.data.detail && <p className="mt-1">{trainingStatus.data.detail}</p>}
              </div>
              <Button variant="outline" onClick={() => { setActiveModelId(null); trainMutation.reset(); }}>Reintentar</Button>
            </div>
          )}
          {activeModelId && trainingStatus.data?.status === "completed" && (
            <div className="space-y-5">
              <div className="flex items-center gap-2 text-sensor-green"><CheckCircle2 className="h-5 w-5" /><p className="font-semibold">Entrenamiento completado</p></div>
              {trainingStatus.data.warnings && trainingStatus.data.warnings.length > 0 && (
                <div className="rounded-lg border border-satellite-amber/20 bg-satellite-amber/10 p-4 text-sm text-satellite-amber">
                  <ul className="list-disc space-y-1 pl-5">{trainingStatus.data.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
                </div>
              )}
              {trainingStatus.data.metrics && Object.keys(trainingStatus.data.metrics).length > 0 && (
                <div>
                  <p className="mb-2 text-sm font-medium">Métricas por objetivo</p>
                  <div className="overflow-x-auto rounded-lg border border-border">
                    <table className="w-full text-left text-sm">
                      <thead className="bg-muted/40">
                        <tr><th className="px-4 py-2 font-medium">Objetivo</th><th className="px-4 py-2 font-medium">MAE</th><th className="px-4 py-2 font-medium">RMSE</th><th className="px-4 py-2 font-medium">R²</th><th className="px-4 py-2 font-medium">Calidad</th></tr>
                      </thead>
                      <tbody>
                        {Object.entries(trainingStatus.data.metrics).map(([target, m]: [string, TargetMetrics]) => {
                          const qualityTone: StatusTone = m.r2 >= 0.7 ? "success" : m.r2 >= 0.5 ? "warning" : "danger";
                          const qualityLabel = m.r2 >= 0.7 ? "Bueno" : m.r2 >= 0.5 ? "Aceptable" : "Bajo";
                          return (
                            <tr key={target} className="border-t border-border">
                              <td className="px-4 py-2 font-medium">{target}</td>
                              <td className="px-4 py-2">{m.mae.toFixed(4)}</td>
                              <td className="px-4 py-2">{m.rmse.toFixed(4)}</td>
                              <td className="px-4 py-2">{m.r2.toFixed(4)}</td>
                              <td className="px-4 py-2"><StatusTag tone={qualityTone}>{qualityLabel}</StatusTag></td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
              <div className="flex flex-wrap gap-3">
                <a href={modelosApi.getDownloadUrl(activeModelId)} download>
                  <Button variant="outline"><Download className="mr-2 h-4 w-4" />Descargar modelo (.zip)</Button>
                </a>
                <Button variant="outline" onClick={() => { setActiveModelId(null); trainMutation.reset(); }}>
                  <Sparkles className="mr-2 h-4 w-4" />Reentrenar
                </Button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
