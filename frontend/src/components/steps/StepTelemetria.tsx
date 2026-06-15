import { useMemo } from "react";
import { Satellite } from "lucide-react";

import { FeatureNode } from "@/components/feature-model/FeatureNode";
import { ParcelMap } from "@/components/config/ParcelMap";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConstraintHints } from "@/components/steps/ConstraintHints";
import { SectionTitle } from "@/components/steps/SectionTitle";
import { useFeatureModelQuery } from "@/hooks/useConfiguratorApi";
import { useFeatureTrees } from "@/hooks/useFeatureTrees";
import { FEATURE_HELP } from "@/lib/featureHelp";
import { useGeo } from "@/hooks/useGeo";
import { collectFeatureNames, getNode, buildLabelMap, buildAccumulatedScope } from "@/utils/featureModel";
import { getViolations, getIncomingRequirements } from "@/utils/constraintEvaluator";

interface StepTelemetriaProps {
  serverErrors: string[];
  isPending: boolean;
  onComplete: () => void;
}

export function StepTelemetria({ serverErrors, isPending, onComplete }: StepTelemetriaProps) {
  const featureModelQuery = useFeatureModelQuery();
  const { trees } = useFeatureTrees();
  const { geo, patchGeo } = useGeo();
  const features = trees[0]?.features ?? [];

  const model = featureModelQuery.data ?? null;
  const telemetriaNode = model ? getNode(model, "DatosTelemetria") : null;

  const subtreeNames = useMemo(
    () => new Set(telemetriaNode ? collectFeatureNames(telemetriaNode) : []),
    [telemetriaNode],
  );

  const accumulatedScope = useMemo(
    () => (model ? buildAccumulatedScope(model, "telemetry") : new Set<string>()),
    [model],
  );

  const labelMap = useMemo(() => (model ? buildLabelMap(model) : new Map<string, string>()), [model]);

  const intraViolations = useMemo(
    () => getViolations(model?.constraints ?? [], subtreeNames, features),
    [model?.constraints, subtreeNames, features],
  );

  const incomingHints = useMemo(
    () => getIncomingRequirements(model?.constraints ?? [], accumulatedScope, features),
    [model?.constraints, accumulatedScope, features],
  );

  const telemetryActive = features.some((f) => subtreeNames.has(f) && f !== "DatosTelemetria" && f !== "Nubes");
  const canComplete = intraViolations.length === 0 && incomingHints.length === 0;

  return (
    <div className="config-block animate-reveal-up" style={{ animationDelay: "140ms" }}>
      <SectionTitle icon={Satellite} title="Datos de telemetría" iconClassName="text-satellite-amber" help={FEATURE_HELP.DatosTelemetria} />

      {telemetriaNode && <FeatureNode node={telemetriaNode} index={0} />}

      <ConstraintHints violations={incomingHints} labelMap={labelMap} />

      <div className="mt-4 max-w-xs space-y-2">
        <Label htmlFor="cloud-threshold">Porcentaje máximo de nubes</Label>
        <Input
          id="cloud-threshold"
          type="number"
          min={0}
          max={100}
          value={geo.cloudThreshold}
          onChange={(e) => patchGeo({ cloudThreshold: Math.min(100, Math.max(0, Number(e.target.value))) })}
        />
        <p className="text-xs text-muted-foreground">
          Imágenes Sentinel-2 con cobertura superior a este valor serán descartadas.
        </p>
      </div>

      {telemetryActive && <ParcelMap />}

      {serverErrors.length > 0 && (
        <div className="mt-4 rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="mb-2 font-medium">Revisa este bloque antes de continuar</p>
          <ul className="list-disc space-y-1 pl-5">
            {serverErrors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      )}

      <div className="mt-4 flex justify-end border-t border-border/60 pt-4">
        <Button type="button" size="sm" onClick={onComplete} disabled={isPending || !canComplete}>
          Listo, continuar
        </Button>
      </div>
    </div>
  );
}
