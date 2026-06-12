import type { FeatureModelNode, FeatureRelation } from "@/types/api";

const WIZARD_STEP_ORDER = ["parcel", "sensors", "telemetry", "objective"] as const;
type WizardStep = (typeof WIZARD_STEP_ORDER)[number];

export function buildLabelMap(node: FeatureModelNode): Map<string, string> {
  const map = new Map<string, string>();
  buildLabelMapRec(node, map);
  return map;
}

function buildLabelMapRec(node: FeatureModelNode, map: Map<string, string>): void {
  const label = node.attributes?.label as string | undefined;
  if (label) map.set(node.name, label);
  for (const relation of node.relations ?? []) {
    for (const child of relation.children ?? []) {
      buildLabelMapRec(child, map);
    }
  }
}

/**
 * Derives the accumulated scope of feature names for a wizard step by reading
 * the UVL wizard_step attributes from the feature model tree. Returns all
 * feature names belonging to steps up to and including upToStep, plus root
 * features that have no wizard_step ancestor (e.g. Entrada).
 */
export function buildAccumulatedScope(model: FeatureModelNode, upToStep: WizardStep): Set<string> {
  const scope = new Set<string>();
  collectRootAndStepFeatures(model, upToStep, scope);
  return scope;
}

function collectRootAndStepFeatures(
  node: FeatureModelNode,
  upToStep: WizardStep,
  scope: Set<string>,
): void {
  const wizardStep = node.attributes?.wizard_step as string | undefined;
  if (wizardStep) {
    const stepIdx = WIZARD_STEP_ORDER.indexOf(wizardStep as WizardStep);
    const limitIdx = WIZARD_STEP_ORDER.indexOf(upToStep);
    if (stepIdx !== -1 && stepIdx <= limitIdx) {
      collectFeatureNames(node).forEach((f) => scope.add(f));
    }
    return; // Don't recurse into children — entire subtree is assigned to this step
  }
  // No wizard_step → root feature (e.g. Entrada); include it always
  scope.add(node.name);
  for (const relation of node.relations ?? []) {
    for (const child of relation.children ?? []) {
      collectRootAndStepFeatures(child, upToStep, scope);
    }
  }
}

export function getRelations(node: FeatureModelNode): FeatureRelation[] {
  return Array.isArray(node?.relations) ? node.relations : [];
}

export function getRelationChildren(node: FeatureModelNode): FeatureModelNode[] {
  return getRelations(node).flatMap((r) => r.children ?? []);
}

export function hasRelations(node: FeatureModelNode): boolean {
  return getRelations(node).length > 0;
}

export function collectFeatureNames(node: FeatureModelNode, mandatoryOnly = false): string[] {
  let names = [node.name];
  for (const relation of getRelations(node)) {
    if (mandatoryOnly && relation.type !== "MANDATORY") continue;
    for (const child of relation.children ?? []) {
      names = names.concat(collectFeatureNames(child, mandatoryOnly));
    }
  }
  return names;
}

export function addFeatureSubtree(features: string[], feature: FeatureModelNode): string[] {
  return [...new Set(features.concat(collectFeatureNames(feature, true)))];
}

export function removeFeatureSubtree(features: string[], feature: FeatureModelNode): string[] {
  const subtree = collectFeatureNames(feature, false);
  return features.filter((name) => !subtree.includes(name));
}

export function getNode(rootNode: FeatureModelNode, featureName: string): FeatureModelNode | null {
  for (const relation of rootNode.relations ?? []) {
    for (const child of relation.children) {
      if (child.name === featureName) return child;
      const found = getNode(child, featureName);
      if (found) return found;
    }
  }
  return null;
}

export interface ObjectiveRecommendation {
  feature: string;
  label: string;
  sensors: string[];
}

/**
 * Derives non-blocking sensor recommendations for the selected objective(s) from
 * the UVL `recommended_sensors` attribute (comma-separated feature names). Sensor
 * names are mapped to their human labels. Returns [] when no objective is selected
 * or the selected objective carries no `recommended_sensors` attribute.
 */
export function buildObjectiveRecommendations(
  model: FeatureModelNode,
  selectedFeatures: string[],
): ObjectiveRecommendation[] {
  const objetivoNode = getNode(model, "VariableObjetivo");
  if (!objetivoNode) return [];

  const objectiveNames = new Set(
    collectFeatureNames(objetivoNode).filter((n) => n !== "VariableObjetivo"),
  );
  const labelMap = buildLabelMap(model);

  const result: ObjectiveRecommendation[] = [];
  for (const feature of selectedFeatures) {
    if (!objectiveNames.has(feature)) continue;
    const node = getNode(model, feature);
    const raw = node?.attributes?.recommended_sensors as string | undefined;
    if (!raw) continue;
    const sensors = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .map((name) => labelMap.get(name) ?? name);
    if (sensors.length === 0) continue;
    result.push({ feature, label: labelMap.get(feature) ?? feature, sensors });
  }
  return result;
}

/**
 * Returns true if every ALTERNATIVE group reachable through MANDATORY paths
 * from node has at least one child in features[]. Stops at OPTIONAL/OR boundaries
 * (those subtrees are only checked if the parent feature is active).
 */
export function allAlternativesSelected(node: FeatureModelNode, features: string[]): boolean {
  const featSet = new Set(features);
  function check(n: FeatureModelNode): boolean {
    for (const rel of getRelations(n)) {
      if (rel.type === "ALTERNATIVE") {
        if (!rel.children.some((c) => featSet.has(c.name))) return false;
      } else if (rel.type === "MANDATORY") {
        for (const child of rel.children) {
          if (!check(child)) return false;
        }
      }
    }
    return true;
  }
  return check(node);
}

export function collectCsvFeatures(
  model: FeatureModelNode,
  activeFeatures: string[],
  excludeNames: Set<string>,
): Array<{ featureName: string; csvCol: string; label: string }> {
  const result: Array<{ featureName: string; csvCol: string; label: string }> = [];
  const parametrosNode = getNode(model, "ParametrosEntrada");
  if (!parametrosNode) return result;
  const activeSet = new Set(activeFeatures);
  collectCsvFeaturesRec(parametrosNode, activeSet, excludeNames, result);
  return result;
}

function collectCsvFeaturesRec(
  node: FeatureModelNode,
  activeSet: Set<string>,
  excludeNames: Set<string>,
  result: Array<{ featureName: string; csvCol: string; label: string }>,
): void {
  if (!excludeNames.has(node.name)) {
    const a = node.attributes ?? {};
    const csvCol = a.csv_col
      ? String(a.csv_col)
      : a.csv_cols
        ? String(a.csv_cols).split(",")[0].trim()
        : null;
    if (csvCol && activeSet.has(node.name)) {
      result.push({ featureName: node.name, csvCol, label: (a.label as string | undefined) ?? node.name });
    }
  }
  for (const rel of getRelations(node)) {
    for (const child of rel.children ?? []) {
      collectCsvFeaturesRec(child, activeSet, excludeNames, result);
    }
  }
}

export function buildTreatmentTrainingThresholds(
  model: FeatureModelNode,
): Record<string, { minReject: number; minWarn: number; minGood: number }> {
  const tratamientoNode = getNode(model, "Tratamiento");
  if (!tratamientoNode) return {};
  const result: Record<string, { minReject: number; minWarn: number; minGood: number }> = {};
  for (const rel of getRelations(tratamientoNode)) {
    for (const child of rel.children ?? []) {
      const a = child.attributes ?? {};
      if (a.min_reject !== undefined && a.min_warn !== undefined && a.min_good !== undefined) {
        result[child.name] = {
          minReject: Number(a.min_reject),
          minWarn: Number(a.min_warn),
          minGood: Number(a.min_good),
        };
      }
    }
  }
  return result;
}

export function buildCsvColumnInfo(
  model: FeatureModelNode,
  parentName: string,
): { aliases: Record<string, string>; dataColumns: string[] } {
  const node = getNode(model, parentName);
  const aliases: Record<string, string> = {};
  const dataColumns: string[] = [];
  if (node) collectCsvColumns(node, aliases, dataColumns);
  return { aliases, dataColumns };
}

function collectCsvColumns(
  node: FeatureModelNode,
  aliases: Record<string, string>,
  dataColumns: string[],
): void {
  const a = node.attributes ?? {};
  if (a.csv_col) {
    const col = String(a.csv_col);
    aliases[col.toLowerCase()] = col;
    dataColumns.push(col);
  } else if (a.csv_cols) {
    for (const col of String(a.csv_cols).split(",").map((s) => s.trim())) {
      aliases[col.toLowerCase()] = col;
      dataColumns.push(col);
    }
  }
  for (const rel of getRelations(node)) {
    for (const child of rel.children ?? []) {
      collectCsvColumns(child, aliases, dataColumns);
    }
  }
}

