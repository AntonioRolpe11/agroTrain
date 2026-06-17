import { Info } from "lucide-react";

import type { ConstraintAST, FeatureConstraint } from "@/types/api";
import { formatConstraintAST } from "@/utils/constraintEvaluator";

interface ConstraintHintsProps {
  violations: FeatureConstraint[];
  labelMap: Map<string, string>;
}

function getLabel(map: Map<string, string>, name: string): string {
  return map.get(name) ?? name;
}

function formatASTNode(ast: ConstraintAST, labelMap: Map<string, string>): string {
  return formatConstraintAST(ast, (name) => getLabel(labelMap, name));
}

export function ConstraintHints({ violations, labelMap }: ConstraintHintsProps) {
  if (violations.length === 0) return null;

  return (
    <div className="mt-3 space-y-2" data-cy="constraint-hints">
      {violations.map((c, i) => {
        const antecedentLabel = formatASTNode(c.ast.left!, labelMap);
        const consequentLabel = formatASTNode(c.ast.right!, labelMap);
        return (
          <div
            key={i}
            data-cy="constraint-hint"
            className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"
          >
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              <span className="font-medium">{antecedentLabel}</span>
              {" requiere "}
              <span className="font-medium">{consequentLabel}</span>
            </span>
          </div>
        );
      })}
    </div>
  );
}
