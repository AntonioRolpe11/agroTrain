import type { ConstraintAST, FeatureConstraint } from "@/types/api";

export function evalAST(ast: ConstraintAST, features: Set<string>): boolean {
  switch (ast.op) {
    case "FEATURE":
      return features.has(ast.name!);
    case "IMPLIES":
      return !evalAST(ast.left!, features) || evalAST(ast.right!, features);
    case "OR":
      return evalAST(ast.left!, features) || evalAST(ast.right!, features);
    case "AND":
      return evalAST(ast.left!, features) && evalAST(ast.right!, features);
    case "NOT":
      return !evalAST(ast.left!, features);
    default:
      return true;
  }
}

export function collectASTFeatures(ast: ConstraintAST): string[] {
  if (ast.op === "FEATURE") return [ast.name!];
  const result: string[] = [];
  if (ast.left) result.push(...collectASTFeatures(ast.left));
  if (ast.right) result.push(...collectASTFeatures(ast.right));
  return result;
}

export function formatConstraintAST(
  ast: ConstraintAST,
  getLabel: (name: string) => string,
  parentOp?: string,
): string {
  if (ast.op === "FEATURE") return getLabel(ast.name!);
  if (ast.op === "AND") {
    const left = formatConstraintAST(ast.left!, getLabel, "AND");
    const right = formatConstraintAST(ast.right!, getLabel, "AND");
    const result = `${left} + ${right}`;
    return parentOp === "OR" ? `(${result})` : result;
  }
  if (ast.op === "OR") {
    const left = formatConstraintAST(ast.left!, getLabel, "OR");
    const right = formatConstraintAST(ast.right!, getLabel, "OR");
    return `${left} o ${right}`;
  }
  if (ast.op === "NOT") return `no ${formatConstraintAST(ast.left!, getLabel, "NOT")}`;
  return "";
}

/**
 * Returns constraints that are fully contained within the given subtree
 * (all features mentioned in the constraint are in subtreeNames) and
 * that are violated by the current feature selection.
 */
export function getViolations(
  constraints: FeatureConstraint[],
  subtreeNames: Set<string>,
  activeFeatures: string[],
): FeatureConstraint[] {
  const active = new Set(activeFeatures);
  return constraints.filter(
    (c) =>
      c.features.every((f) => subtreeNames.has(f)) &&
      !evalAST(c.ast, active),
  );
}

/**
 * Returns violated IMPLIES constraints where:
 * - The antecedent is fully active (selected)
 * - The constraint is violated (consequent not satisfied)
 * - At least one consequent feature is within accumulatedScopeNames
 *   (so the hint is actionable in the current or earlier steps)
 *
 * Used to surface cross-step requirements inline in each wizard step.
 */
export function getIncomingRequirements(
  constraints: FeatureConstraint[],
  accumulatedScopeNames: Set<string>,
  activeFeatures: string[],
): FeatureConstraint[] {
  const active = new Set(activeFeatures);
  return constraints.filter((c) => {
    if (c.ast.op !== "IMPLIES") return false;
    const antecedentFeatures = collectASTFeatures(c.ast.left!);
    if (!antecedentFeatures.every((f) => active.has(f))) return false;
    if (evalAST(c.ast, active)) return false;
    const consequentFeatures = collectASTFeatures(c.ast.right!);
    return consequentFeatures.some((f) => accumulatedScopeNames.has(f));
  });
}
