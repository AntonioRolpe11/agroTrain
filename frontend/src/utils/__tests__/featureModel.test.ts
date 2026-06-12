import { describe, it, expect } from "vitest";
import {
  addFeatureSubtree,
  allAlternativesSelected,
  buildAccumulatedScope,
  buildCsvColumnInfo,
  buildLabelMap,
  buildObjectiveRecommendations,
  buildTreatmentTrainingThresholds,
  collectCsvFeatures,
  collectFeatureNames,
  getNode,
  removeFeatureSubtree,
} from "@/utils/featureModel";
import type { FeatureModelNode } from "@/types/api";

const tree: FeatureModelNode = {
  name: "Entrada",
  attributes: {},
  relations: [
    {
      type: "MANDATORY",
      children: [
        {
          name: "DatosParcela",
          attributes: { wizard_step: "parcel" },
          relations: [
            {
              type: "MANDATORY",
              children: [
                {
                  name: "Tratamiento",
                  attributes: { label: "Tratamiento" },
                  relations: [
                    {
                      type: "ALTERNATIVE",
                      children: [
                        { name: "Secano", attributes: { label: "Secano", min_reject: 10, min_warn: 20, min_good: 50 }, relations: [] },
                        { name: "Riego", attributes: { label: "Riego", min_reject: 20, min_warn: 30, min_good: 70 }, relations: [] },
                      ],
                    },
                  ],
                },
              ],
            },
          ],
        },
        {
          name: "ParametrosEntrada",
          attributes: { wizard_step: "sensors" },
          relations: [
            {
              type: "OPTIONAL",
              children: [
                { name: "DPV", attributes: { label: "DPV", csv_col: "dpv" }, relations: [] },
                { name: "TempAire", attributes: { label: "Temperatura", csv_cols: "tmax,tmin" }, relations: [] },
              ],
            },
          ],
        },
        {
          name: "DatosTelemetria",
          attributes: { wizard_step: "telemetry" },
          relations: [
            {
              type: "OPTIONAL",
              children: [
                { name: "NDVI", attributes: { csv_col: "NDVI" }, relations: [] },
              ],
            },
          ],
        },
      ],
    },
  ],
};

describe("buildLabelMap", () => {
  it("reads labels recursively", () => {
    const map = buildLabelMap(tree);
    expect(map.get("Tratamiento")).toBe("Tratamiento");
    expect(map.get("Secano")).toBe("Secano");
    expect(map.get("DPV")).toBe("DPV");
  });
});

describe("buildAccumulatedScope", () => {
  it("includes only parcel features at parcel step", () => {
    const scope = buildAccumulatedScope(tree, "parcel");
    expect(scope.has("Entrada")).toBe(true);
    expect(scope.has("DatosParcela")).toBe(true);
    expect(scope.has("Secano")).toBe(true);
    expect(scope.has("DPV")).toBe(false);
    expect(scope.has("NDVI")).toBe(false);
  });

  it("includes sensors features at sensors step", () => {
    const scope = buildAccumulatedScope(tree, "sensors");
    expect(scope.has("DPV")).toBe(true);
    expect(scope.has("NDVI")).toBe(false);
  });

  it("includes telemetry features at telemetry step", () => {
    const scope = buildAccumulatedScope(tree, "telemetry");
    expect(scope.has("NDVI")).toBe(true);
  });
});

describe("collectFeatureNames", () => {
  it("returns full subtree by default", () => {
    const names = collectFeatureNames(tree);
    expect(names).toContain("Entrada");
    expect(names).toContain("DPV");
    expect(names).toContain("NDVI");
  });

  it("mandatoryOnly skips ALTERNATIVE and OPTIONAL", () => {
    const names = collectFeatureNames(tree, true);
    expect(names).toContain("Entrada");
    expect(names).toContain("DatosParcela");
    expect(names).not.toContain("Secano");  // ALTERNATIVE
    expect(names).not.toContain("DPV");     // OPTIONAL
  });
});

describe("getNode", () => {
  it("finds nested features", () => {
    expect(getNode(tree, "Secano")?.name).toBe("Secano");
    expect(getNode(tree, "NDVI")?.name).toBe("NDVI");
  });

  it("returns null when not present", () => {
    expect(getNode(tree, "Unknown")).toBeNull();
  });
});

describe("addFeatureSubtree / removeFeatureSubtree", () => {
  it("adds mandatory subtree only", () => {
    const tratamiento = getNode(tree, "Tratamiento")!;
    const updated = addFeatureSubtree([], tratamiento);
    expect(updated).toContain("Tratamiento");
    expect(updated).not.toContain("Secano");
  });

  it("removes full subtree", () => {
    const dp = getNode(tree, "DatosParcela")!;
    const updated = removeFeatureSubtree(["DatosParcela", "Tratamiento", "Secano", "Other"], dp);
    expect(updated).toEqual(["Other"]);
  });
});

describe("allAlternativesSelected", () => {
  it("returns true when alternative chosen", () => {
    expect(allAlternativesSelected(tree, ["Secano"])).toBe(true);
  });

  it("returns false when no alternative chosen", () => {
    expect(allAlternativesSelected(tree, [])).toBe(false);
  });
});

describe("collectCsvFeatures", () => {
  it("returns active sensors with csv columns, excluding hardcoded names", () => {
    const result = collectCsvFeatures(tree, ["DPV", "TempAire"], new Set(["TempAire"]));
    expect(result).toHaveLength(1);
    expect(result[0].featureName).toBe("DPV");
    expect(result[0].csvCol).toBe("dpv");
  });
});

describe("buildTreatmentTrainingThresholds", () => {
  it("extracts min_reject/min_warn/min_good per treatment", () => {
    const th = buildTreatmentTrainingThresholds(tree);
    expect(th.Secano).toEqual({ minReject: 10, minWarn: 20, minGood: 50 });
    expect(th.Riego.minGood).toBe(70);
  });
});

describe("buildCsvColumnInfo", () => {
  it("builds alias map for DatosTelemetria subtree", () => {
    const { aliases, dataColumns } = buildCsvColumnInfo(tree, "DatosTelemetria");
    expect(dataColumns).toContain("NDVI");
    expect(aliases.ndvi).toBe("NDVI");
  });

  it("supports csv_cols (comma-separated)", () => {
    const { aliases, dataColumns } = buildCsvColumnInfo(tree, "ParametrosEntrada");
    expect(dataColumns).toContain("tmax");
    expect(dataColumns).toContain("tmin");
    expect(aliases.tmax).toBe("tmax");
  });

  it("returns empty when parent not found", () => {
    const result = buildCsvColumnInfo(tree, "Unknown");
    expect(result.dataColumns).toEqual([]);
  });
});

const objetivoTree: FeatureModelNode = {
  name: "Entrada",
  attributes: {},
  relations: [
    {
      type: "MANDATORY",
      children: [
        {
          name: "ParametrosEntrada",
          attributes: {},
          relations: [
            {
              type: "OPTIONAL",
              children: [
                { name: "Dendrometro", attributes: { label: "Dendrómetro" }, relations: [] },
                { name: "Pluviometro", attributes: { label: "Pluviómetro" }, relations: [] },
              ],
            },
          ],
        },
        {
          name: "VariableObjetivo",
          attributes: { label: "Variable objetivo" },
          relations: [
            {
              type: "ALTERNATIVE",
              children: [
                {
                  name: "TasaBuenos",
                  attributes: { label: "Tasa de buenos", recommended_sensors: "Dendrometro,Pluviometro" },
                  relations: [],
                },
                { name: "MCD", attributes: { label: "MCD" }, relations: [] },
              ],
            },
          ],
        },
      ],
    },
  ],
};

describe("buildObjectiveRecommendations", () => {
  it("maps recommended_sensors of the selected objective to labels", () => {
    const recs = buildObjectiveRecommendations(objetivoTree, ["TasaBuenos"]);
    expect(recs).toHaveLength(1);
    expect(recs[0].feature).toBe("TasaBuenos");
    expect(recs[0].label).toBe("Tasa de buenos");
    expect(recs[0].sensors).toEqual(["Dendrómetro", "Pluviómetro"]);
  });

  it("returns [] when selected objective has no recommended_sensors", () => {
    expect(buildObjectiveRecommendations(objetivoTree, ["MCD"])).toEqual([]);
  });

  it("returns [] when no objective is selected", () => {
    expect(buildObjectiveRecommendations(objetivoTree, ["Dendrometro"])).toEqual([]);
  });
});
