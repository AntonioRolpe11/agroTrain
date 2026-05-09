import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, BookOpen, CheckCircle2, Save, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

import { ParcelDataCard } from "@/components/config/ParcelDataCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StepObjetivo } from "@/components/steps/StepObjetivo";
import { StepSensores } from "@/components/steps/StepSensores";
import { StepTelemetria } from "@/components/steps/StepTelemetria";
import type { PartialValidationStep } from "@/types/api";
import type { GeoData } from "@/lib/geoContext";
import { useFeatureModelQuery, useValidateFeaturesMutation } from "@/hooks/useConfiguratorApi";
import { useFeatureTrees } from "@/hooks/useFeatureTrees";
import { useGeo } from "@/hooks/useGeo";
import { useConfiguracionesQuery, useEliminarConfiguracion, useGuardarConfiguracion } from "@/hooks/useConfiguraciones";
import { allAlternativesSelected, collectFeatureNames, getNode } from "@/utils/featureModel";

function StepLockedHint({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-muted/20 p-4 text-sm text-muted-foreground">
      {text}
    </div>
  );
}

export default function DigitalSensorCreation() {
  const navigate = useNavigate();
  const featureModelQuery = useFeatureModelQuery();
  const validateMutation = useValidateFeaturesMutation();
  const { trees, setTrees } = useFeatureTrees();
  const { geo, patchGeo, resetGeo } = useGeo();

  const features = trees[0]?.features ?? [];
  const model = featureModelQuery.data ?? null;

  const [unlockedStepIndex, setUnlockedStepIndex] = useState(0);
  const [serverErrors, setServerErrors] = useState<string[]>([]);
  const [errorStep, setErrorStep] = useState<string | null>(null);

  const importInputRef = useRef<HTMLInputElement>(null);

  // Guardar/cargar configuración en servidor
  const configsQuery = useConfiguracionesQuery();
  const guardarMut = useGuardarConfiguracion();
  const eliminarMut = useEliminarConfiguracion();
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [showLoadPanel, setShowLoadPanel] = useState(false);
  const [saveName, setSaveName] = useState("");

  const parcelRef = useRef<HTMLDivElement>(null);
  const sensorsRef = useRef<HTMLDivElement>(null);
  const telemetryRef = useRef<HTMLDivElement>(null);
  const objectiveRef = useRef<HTMLDivElement>(null);
  const stepRefs = [parcelRef, sensorsRef, telemetryRef, objectiveRef];
  const prevUnlocked = useRef(unlockedStepIndex);

  // Seed mandatory features once on model load
  useEffect(() => {
    if (!model) return;
    setTrees((prev) => {
      if ((prev[0]?.features.length ?? 0) > 0) return prev;
      return [{ features: collectFeatureNames(model, true) }];
    });
  }, [model, setTrees]);

  // Clear errors when selection changes
  useEffect(() => {
    setServerErrors([]);
    setErrorStep(null);
  }, [features, geo]);

  // Scroll to newly unlocked step
  useEffect(() => {
    if (unlockedStepIndex > prevUnlocked.current) {
      const ref = stepRefs[unlockedStepIndex];
      window.requestAnimationFrame(() =>
        ref?.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    }
    prevUnlocked.current = unlockedStepIndex;
  }, [unlockedStepIndex]); // eslint-disable-line react-hooks/exhaustive-deps

  // Parcel step readiness — all mandatory ALTERNATIVE groups selected + geo
  const parcelaNode = model ? getNode(model, "DatosParcela") : null;
  const parcelFeaturesOk = parcelaNode ? allAlternativesSelected(parcelaNode, features) : false;
  const parcelStepReady = parcelFeaturesOk && Boolean(geo.provinciaId) && Boolean(geo.municipioId) && Boolean(geo.punto);

  const stepServerErrors = (step: string) => (errorStep === step ? serverErrors : []);

  const STEP_NAMES: PartialValidationStep[] = ["parcel", "sensors", "telemetry", "objective"];

  const handleCompleteStep = async (stepIndex: number) => {
    setServerErrors([]);
    setErrorStep(null);
    try {
      const step = STEP_NAMES[stepIndex];
      const response = await validateMutation.mutateAsync({ features, is_full: false, step });
      if (!response.valid) {
        setServerErrors(response.errors);
        setErrorStep(String(stepIndex));
        return;
      }
      setUnlockedStepIndex(stepIndex + 1);
    } catch (err) {
      setServerErrors([err instanceof Error ? err.message : "Error desconocido validando el paso."]);
      setErrorStep(String(stepIndex));
    }
  };

  const handleGenerate = async () => {
    setServerErrors([]);
    setErrorStep(null);
    try {
      const response = await validateMutation.mutateAsync({ features, is_full: true, step: "full" });
      if (!response.valid) {
        setServerErrors(response.errors);
        setErrorStep("full");
        return;
      }
      navigate("/validacion-modelo");
    } catch (err) {
      setServerErrors([err instanceof Error ? err.message : "Error desconocido validando con el backend."]);
      setErrorStep("full");
    }
  };

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !model) return;
    e.target.value = "";
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const parsed = JSON.parse(ev.target?.result as string) as { version?: number; features?: unknown; geo?: unknown };
        if (parsed.version !== 1 || !Array.isArray(parsed.features) || typeof parsed.geo !== "object") {
          toast.error("Formato inválido", { description: "El archivo no es una configuración válida (versión 1)." });
          return;
        }
        const allModelFeatures = new Set(collectFeatureNames(model));
        const importedFeatures = parsed.features as string[];
        const unknown = importedFeatures.filter((f) => !allModelFeatures.has(f));
        if (unknown.length > 0) {
          toast.error("Configuración incompatible", { description: `Features no reconocidas en el modelo actual: ${unknown.join(", ")}` });
          return;
        }
        setTrees([{ features: importedFeatures }]);
        const importedGeo = parsed.geo as Partial<GeoData>;
        patchGeo({
          nombre: importedGeo.nombre ?? "",
          provinciaId: importedGeo.provinciaId ?? null,
          provinciaNombre: importedGeo.provinciaNombre ?? null,
          municipioId: importedGeo.municipioId ?? null,
          municipioNombre: importedGeo.municipioNombre ?? null,
          punto: importedGeo.punto ?? null,
          cloudThreshold: importedGeo.cloudThreshold ?? 20,
        });
        setUnlockedStepIndex(importedGeo.provinciaId && importedGeo.municipioId && importedGeo.punto ? 1 : 0);
        setServerErrors([]);
        setErrorStep(null);
        toast.success("Configuración importada", { description: `${importedFeatures.length} features restauradas.` });
      } catch {
        toast.error("No se pudo leer el archivo", { description: "Asegúrate de que es un JSON válido." });
      }
    };
    reader.readAsText(file);
  };

  const handleSaveToServer = async () => {
    if (!saveName.trim()) return;
    try {
      await guardarMut.mutateAsync({ nombre: saveName.trim(), features, geo });
      toast.success("Configuración guardada.");
      setSaveName("");
      setShowSaveDialog(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Error al guardar.");
    }
  };

  const handleLoadFromServer = (cfg: { features: string[]; geo: Record<string, unknown> }) => {
    if (!model) return;
    const allModelFeatures = new Set(collectFeatureNames(model));
    const unknown = cfg.features.filter((f) => !allModelFeatures.has(f));
    if (unknown.length > 0) {
      toast.error("Configuración incompatible", { description: `Features no reconocidas: ${unknown.join(", ")}` });
      return;
    }
    setTrees([{ features: cfg.features }]);
    const g = cfg.geo as Partial<GeoData>;
    patchGeo({
      nombre: g.nombre ?? "",
      provinciaId: g.provinciaId ?? null,
      provinciaNombre: g.provinciaNombre ?? null,
      municipioId: g.municipioId ?? null,
      municipioNombre: g.municipioNombre ?? null,
      punto: g.punto ?? null,
      cloudThreshold: (g.cloudThreshold as number) ?? 20,
    });
    setUnlockedStepIndex(g.provinciaId && g.municipioId && g.punto ? 1 : 0);
    setServerErrors([]);
    setErrorStep(null);
    setShowLoadPanel(false);
    toast.success("Configuración cargada.");
  };

  const handleReset = () => {
    if (model) setTrees([{ features: collectFeatureNames(model, true) }]);
    resetGeo();
    setServerErrors([]);
    setErrorStep(null);
    setUnlockedStepIndex(0);
  };

  const hasErrors = serverErrors.length > 0;
  const hasSuccess = !hasErrors && unlockedStepIndex >= 4;

  return (
    <div className="w-full px-[36px] py-10 sm:px-[44px] lg:px-[52px] xl:px-[60px] 2xl:px-[400px]">
      <div className="w-full">
        <div className="animate-reveal-up mb-6 space-y-2">
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-border bg-muted/20 px-4 py-3">
            <p className="text-sm text-muted-foreground flex-1 min-w-0">Restaura una configuración guardada.</p>
            <div className="flex flex-wrap gap-2 shrink-0">
              <input ref={importInputRef} type="file" accept=".json" className="hidden" onChange={handleImport} />
              <Button variant="outline" size="sm" onClick={() => importInputRef.current?.click()}>
                <Upload className="mr-2 h-4 w-4" />Importar JSON
              </Button>
              <Button variant="outline" size="sm" onClick={() => { setShowLoadPanel((v) => !v); setShowSaveDialog(false); }}>
                <BookOpen className="mr-2 h-4 w-4" />Mis configuraciones
              </Button>
            </div>
          </div>

          {showLoadPanel && (
            <div className="rounded-lg border border-border bg-card">
              {configsQuery.isLoading ? (
                <p className="px-4 py-3 text-sm text-muted-foreground">Cargando...</p>
              ) : (configsQuery.data?.length ?? 0) === 0 ? (
                <p className="px-4 py-3 text-sm text-muted-foreground">No tienes configuraciones guardadas.</p>
              ) : (
                <ul className="divide-y divide-border">
                  {configsQuery.data!.map((cfg) => (
                    <li key={cfg.id} className="flex items-center justify-between px-4 py-2 gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{cfg.nombre}</p>
                        <p className="text-xs text-muted-foreground">
                          {new Date(cfg.updated_at).toLocaleString("es-ES")}
                        </p>
                      </div>
                      <div className="flex gap-1 shrink-0">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleLoadFromServer({ features: cfg.features, geo: cfg.geo })}
                        >
                          Cargar
                        </Button>
                        <button
                          title="Eliminar"
                          className="p-1.5 text-muted-foreground hover:text-destructive transition-colors"
                          onClick={() => { if (confirm(`¿Eliminar "${cfg.nombre}"?`)) eliminarMut.mutate(cfg.id); }}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <h1 className="animate-reveal-up mb-2 text-3xl font-bold">Creación de sensor digital</h1>
        <p className="animate-reveal-up mb-8 text-muted-foreground" style={{ animationDelay: "60ms" }}>
          Configura entradas, objetivo y, cuando haya telemetría, los datos básicos de la parcela. Las salidas base
          son obligatorias por el UVL.
        </p>

        <div
          className={`mb-6 rounded-lg border p-4 ${
            hasSuccess
              ? "border-sensor-green/20 bg-sensor-green/10 text-sensor-green"
              : hasErrors
                ? "border-destructive/20 bg-destructive/10 text-destructive"
                : "border-border bg-muted/20 text-muted-foreground"
          }`}
        >
          <div className="flex items-start gap-2">
            {hasSuccess ? (
              <CheckCircle2 className="mt-0.5 h-5 w-5" />
            ) : (
              <AlertTriangle className="mt-0.5 h-5 w-5" />
            )}
            <div>
              <p className="text-sm font-medium">
                {hasSuccess
                  ? "Configuración lista para validar el modelo"
                  : hasErrors
                    ? "Hay errores pendientes en el paso actual"
                    : "Completa cada bloque y usa 'Listo' para avanzar paso a paso"}
              </p>
              <p className="mt-1 text-sm">
                {hasErrors
                  ? "Los detalles se muestran debajo del contenedor donde se produjo el error."
                  : "La validación detallada aparecerá justo debajo del bloque que estés completando."}
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          {/* Paso 1: Parcela */}
          <div ref={parcelRef}>
            <ParcelDataCard
              footer={
                <Button
                  type="button"
                  onClick={() => setUnlockedStepIndex(1)}
                  disabled={!parcelStepReady}
                >
                  Listo, continuar a sensores físicos
                </Button>
              }
            />
          </div>

          {unlockedStepIndex < 1 && (
            <StepLockedHint text="Selecciona tratamiento, tipo de suelo, provincia y municipio y pulsa Listo para desbloquear los sensores físicos." />
          )}

          {/* Paso 2: Sensores */}
          {unlockedStepIndex >= 1 && (
            <div ref={sensorsRef}>
              <StepSensores
                serverErrors={stepServerErrors("1")}
                isPending={validateMutation.isPending}
                onComplete={() => void handleCompleteStep(1)}
              />
            </div>
          )}

          {unlockedStepIndex >= 1 && unlockedStepIndex < 2 && (
            <StepLockedHint text="Configura los sensores físicos y pulsa Listo para continuar con la telemetría." />
          )}

          {/* Paso 3: Telemetría */}
          {unlockedStepIndex >= 2 && (
            <div ref={telemetryRef}>
              <StepTelemetria
                serverErrors={stepServerErrors("2")}
                isPending={validateMutation.isPending}
                onComplete={() => void handleCompleteStep(2)}
              />
            </div>
          )}

          {unlockedStepIndex >= 2 && unlockedStepIndex < 3 && (
            <StepLockedHint text="Elige telemetría o continúa sin ella y pulsa Listo para elegir la variable objetivo." />
          )}

          {/* Paso 4: Objetivo + Validar */}
          {unlockedStepIndex >= 3 && (
            <div ref={objectiveRef}>
              <StepObjetivo
                serverErrors={[...stepServerErrors("3"), ...stepServerErrors("full")]}
                isValidating={validateMutation.isPending}
                isResetting={false}
                onReset={handleReset}
                onGenerate={() => void handleGenerate()}
              />
            </div>
          )}
        </div>

        {/* Guardar configuración */}
        <div className="mt-8 space-y-2">
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-border bg-muted/20 px-4 py-3">
            <p className="text-sm text-muted-foreground flex-1 min-w-0">Guarda la configuración actual en el servidor.</p>
            <Button variant="outline" size="sm" onClick={() => { setShowSaveDialog((v) => !v); }}>
              <Save className="mr-2 h-4 w-4" />Guardar configuración
            </Button>
          </div>

          {showSaveDialog && (
            <div className="flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-3">
              <Input
                className="flex-1"
                placeholder="Nombre de la configuración..."
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") void handleSaveToServer(); }}
                autoFocus
              />
              <Button size="sm" disabled={!saveName.trim() || guardarMut.isPending} onClick={() => void handleSaveToServer()}>
                {guardarMut.isPending ? "Guardando..." : "Guardar"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowSaveDialog(false)}>Cancelar</Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
