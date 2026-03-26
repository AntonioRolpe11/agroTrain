import { useMemo } from "react";
import { Droplets } from "lucide-react";

import { FeatureNode } from "@/components/feature-model/FeatureNode";
import { Button } from "@/components/ui/button";
import { ConstraintHints } from "@/components/steps/ConstraintHints";
import { SectionTitle } from "@/components/steps/SectionTitle";
import { useFeatureModelQuery } from "@/hooks/useConfiguratorApi";
import { useFeatureTrees } from "@/hooks/useFeatureTrees";
import { collectFeatureNames, getNode, buildLabelMap, buildAccumulatedScope } from "@/utils/featureModel";
import { getViolations, getIncomingRequirements } from "@/utils/constraintEvaluator";

interface StepSensoresProps {
  serverErrors: string[];
  isPending: boolean;
  onComplete: () => void;
}

export function StepSensores({ serverErrors, isPending, onComplete }: StepSensoresProps) {
  const featureModelQuery = useFeatureModelQuery();
  const { trees } = useFeatureTrees();
  const features = trees[0]?.features ?? [];

  const model = featureModelQuery.data ?? null;
  const parametrosNode = model ? getNode(model, "ParametrosEntrada") : null;

  const subtreeNames = useMemo(
    () => new Set(parametrosNode ? collectFeatureNames(parametrosNode) : []),
    [parametrosNode],
  );

  const accumulatedScope = useMemo(
    () => (model ? buildAccumulatedScope(model, "sensors") : new Set<string>()),
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

  const canComplete = intraViolations.length === 0 && incomingHints.length === 0;

  return (
    <div className="config-block animate-reveal-up" style={{ animationDelay: "100ms" }}>
      <SectionTitle icon={Droplets} title="Parámetros de entrada" iconClassName="text-sensor-green" />

      {parametrosNode && <FeatureNode node={parametrosNode} index={0} />}

      <ConstraintHints violations={incomingHints} labelMap={labelMap} />

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
