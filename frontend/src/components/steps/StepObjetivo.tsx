import { useMemo } from "react";
import { Lightbulb, Loader2, Sparkles, Target } from "lucide-react";

import { FeatureNode } from "@/components/feature-model/FeatureNode";
import { Button } from "@/components/ui/button";
import { ConstraintHints } from "@/components/steps/ConstraintHints";
import { SectionTitle } from "@/components/steps/SectionTitle";
import { useFeatureModelQuery } from "@/hooks/useConfiguratorApi";
import { useFeatureTrees } from "@/hooks/useFeatureTrees";
import {
  collectFeatureNames,
  getNode,
  buildLabelMap,
  buildAccumulatedScope,
  buildObjectiveRecommendations,
} from "@/utils/featureModel";
import { getIncomingRequirements } from "@/utils/constraintEvaluator";

interface StepObjetivoProps {
  serverErrors: string[];
  isValidating: boolean;
  isResetting: boolean;
  onReset: () => void;
  onGenerate: () => void;
}

export function StepObjetivo({
  serverErrors,
  isValidating,
  isResetting,
  onReset,
  onGenerate,
}: StepObjetivoProps) {
  const featureModelQuery = useFeatureModelQuery();
  const { trees } = useFeatureTrees();
  const features = trees[0]?.features ?? [];
  const isPending = isValidating || isResetting;

  const model = featureModelQuery.data ?? null;
  const objetivoNode = model ? getNode(model, "VariableObjetivo") : null;

  const childNames = useMemo(() => {
    if (!objetivoNode) return new Set<string>();
    return new Set(collectFeatureNames(objetivoNode).filter((n) => n !== "VariableObjetivo"));
  }, [objetivoNode]);

  const accumulatedScope = useMemo(
    () => (model ? buildAccumulatedScope(model, "objective") : new Set<string>()),
    [model],
  );

  const labelMap = useMemo(() => (model ? buildLabelMap(model) : new Map<string, string>()), [model]);

  const incomingHints = useMemo(
    () => getIncomingRequirements(model?.constraints ?? [], accumulatedScope, features),
    [model?.constraints, accumulatedScope, features],
  );

  const recommendations = useMemo(
    () => (model ? buildObjectiveRecommendations(model, features) : []),
    [model, features],
  );

  const hasObjective = features.some((f) => childNames.has(f));

  return (
    <div className="config-block animate-reveal-up" style={{ animationDelay: "200ms" }}>
      <SectionTitle icon={Target} title="Variable objetivo" iconClassName="text-olive" />

      {objetivoNode && <FeatureNode node={objetivoNode} index={0} />}

      <ConstraintHints violations={incomingHints} labelMap={labelMap} />

      {recommendations.length > 0 && (
        <div className="mt-3 space-y-2">
          {recommendations.map((r) => (
            <div
              key={r.feature}
              className="flex items-start gap-2 rounded-md border border-sky-200 bg-sky-50 p-3 text-sm text-sky-800"
            >
              <Lightbulb className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                Para <span className="font-medium">{r.label}</span> se recomienda usar{" "}
                <span className="font-medium">{r.sensors.join(", ")}</span>, que suelen dar
                las mejores predicciones para este objetivo.
              </span>
            </div>
          ))}
        </div>
      )}

      {serverErrors.length > 0 && (
        <div className="mt-4 rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="mb-2 font-medium">Revisa este bloque antes de continuar</p>
          <ul className="list-disc space-y-1 pl-5">
            {serverErrors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-3">
        <Button variant="outline" onClick={onReset} disabled={isPending}>
          Reiniciar formulario
        </Button>
        <Button
          disabled={!hasObjective || isPending}
          onClick={onGenerate}
          className="transition-transform active:scale-[0.97]"
        >
          {isValidating ? (
            <Loader2 className="mr-1 h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="mr-1 h-4 w-4" />
          )}
          Validar configuración
        </Button>
      </div>
    </div>
  );
}
