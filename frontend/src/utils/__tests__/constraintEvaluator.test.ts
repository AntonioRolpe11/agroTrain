import { describe, it, expect } from "vitest";
import {
  collectASTFeatures,
  evalAST,
  formatConstraintAST,
  getIncomingRequirements,
  getViolations,
} from "@/utils/constraintEvaluator";
import type { ConstraintAST, FeatureConstraint } from "@/types/api";

const F = (name: string): ConstraintAST => ({ op: "FEATURE", name });
const implies = (left: ConstraintAST, right: ConstraintAST): ConstraintAST => ({
  op: "IMPLIES",
  left,
  right,
});
const or = (left: ConstraintAST, right: ConstraintAST): ConstraintAST => ({ op: "OR", left, right });
const and = (left: ConstraintAST, right: ConstraintAST): ConstraintAST => ({ op: "AND", left, right });
const not = (left: ConstraintAST): ConstraintAST => ({ op: "NOT", left });

describe("evalAST", () => {
  it("evaluates FEATURE presence", () => {
    expect(evalAST(F("A"), new Set(["A"]))).toBe(true);
    expect(evalAST(F("A"), new Set())).toBe(false);
  });

  it("evaluates IMPLIES", () => {
    expect(evalAST(implies(F("A"), F("B")), new Set(["A"]))).toBe(false);
    expect(evalAST(implies(F("A"), F("B")), new Set(["A", "B"]))).toBe(true);
    expect(evalAST(implies(F("A"), F("B")), new Set())).toBe(true); // antecedent false
  });

  it("evaluates OR", () => {
    expect(evalAST(or(F("A"), F("B")), new Set(["B"]))).toBe(true);
    expect(evalAST(or(F("A"), F("B")), new Set())).toBe(false);
  });

  it("evaluates AND", () => {
    expect(evalAST(and(F("A"), F("B")), new Set(["A", "B"]))).toBe(true);
    expect(evalAST(and(F("A"), F("B")), new Set(["A"]))).toBe(false);
  });

  it("evaluates NOT", () => {
    expect(evalAST(not(F("A")), new Set())).toBe(true);
    expect(evalAST(not(F("A")), new Set(["A"]))).toBe(false);
  });
});

describe("collectASTFeatures", () => {
  it("collects feature names from nested AST", () => {
    const ast = implies(F("A"), and(F("B"), or(F("C"), F("D"))));
    expect(collectASTFeatures(ast).sort()).toEqual(["A", "B", "C", "D"]);
  });
});

describe("formatConstraintAST", () => {
  const labels = (name: string) => `Lbl${name}`;

  it("formats a feature with its label", () => {
    expect(formatConstraintAST(F("X"), labels)).toBe("LblX");
  });

  it("formats AND with + and OR with 'o'", () => {
    const ast = and(F("X"), or(F("Y"), F("Z")));
    expect(formatConstraintAST(ast, labels)).toBe("LblX + LblY o LblZ");
  });

  it("parenthesizes AND nested inside OR", () => {
    const ast = or(and(F("X"), F("Y")), F("Z"));
    expect(formatConstraintAST(ast, labels)).toBe("(LblX + LblY) o LblZ");
  });

  it("formats NOT", () => {
    expect(formatConstraintAST(not(F("X")), labels)).toBe("no LblX");
  });
});

describe("getViolations", () => {
  it("only reports constraints fully within scope", () => {
    const c1: FeatureConstraint = { features: ["A", "B"], ast: implies(F("A"), F("B")) };
    const c2: FeatureConstraint = { features: ["A", "Z"], ast: implies(F("A"), F("Z")) };
    const violations = getViolations([c1, c2], new Set(["A", "B"]), ["A"]);
    expect(violations).toHaveLength(1);
    expect(violations[0]).toBe(c1);
  });
});

describe("getIncomingRequirements", () => {
  it("only flags IMPLIES whose antecedent is active and consequent touches scope", () => {
    const c: FeatureConstraint = { features: ["A", "B"], ast: implies(F("A"), F("B")) };
    expect(getIncomingRequirements([c], new Set(["B"]), ["A"])).toHaveLength(1);
  });

  it("ignores when antecedent not selected", () => {
    const c: FeatureConstraint = { features: ["A", "B"], ast: implies(F("A"), F("B")) };
    expect(getIncomingRequirements([c], new Set(["B"]), [])).toHaveLength(0);
  });

  it("ignores when consequent outside scope", () => {
    const c: FeatureConstraint = { features: ["A", "B"], ast: implies(F("A"), F("B")) };
    expect(getIncomingRequirements([c], new Set(["X"]), ["A"])).toHaveLength(0);
  });
});
