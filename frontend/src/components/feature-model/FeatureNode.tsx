import { Check } from "lucide-react";

import { cn } from "@/lib/utils";
import type { FeatureModelNode } from "@/types/api";
import { getRelations, hasRelations } from "@/utils/featureModel";
import { useFeatureTrees } from "@/hooks/useFeatureTrees";

type RelationType = "MANDATORY" | "ALTERNATIVE" | "OR" | "OPTIONAL";

const RELATION_CONFIG: Record<RelationType, { title: string | null; hint: string | null; controlType: string }> = {
  MANDATORY:  { title: null,           hint: null,                      controlType: "mandatory" },
  ALTERNATIVE:{ title: "Elige uno",    hint: "Selecciona una opción",   controlType: "radio"     },
  OR:         { title: "Elige uno o más", hint: null,                   controlType: "checkbox"  },
  OPTIONAL:   { title: "Opcionales",   hint: null,                      controlType: "checkbox"  },
};

const MERGEABLE: Set<RelationType> = new Set(["MANDATORY", "OPTIONAL"]);

interface FeatureNodeProps {
  node: FeatureModelNode;
  index?: number;
  depth?: number;
  readOnly?: boolean;
  labelMap?: Record<string, string>;
}

export function FeatureNode({ node, index = 0, depth = 0, readOnly = false, labelMap }: FeatureNodeProps) {
  const { isActive, handleToggle, handleRadioChange } = useFeatureTrees();

  const relations = getRelations(node);
  if (!relations.length) return null;

  const displayRelations = relations.reduce<typeof relations>((grouped, relation) => {
    if (!MERGEABLE.has(relation.type as RelationType)) {
      grouped.push(relation);
      return grouped;
    }
    const existing = grouped.find((g) => g.type === relation.type);
    if (!existing) {
      grouped.push({ ...relation, children: [...(relation.children ?? [])] });
      return grouped;
    }
    existing.children = existing.children.concat(relation.children ?? []);
    return grouped;
  }, []);

  return (
    <div className={cn("w-full space-y-4", readOnly && "pointer-events-none")}>
      {displayRelations.map((relation, relationIndex) => {
        const children = relation.children ?? [];
        if (!children.length) return null;

        const config = RELATION_CONFIG[relation.type as RelationType] ?? {
          title: null, hint: null, controlType: "checkbox",
        };
        const { title, hint, controlType } = config;

        const isMandatory = controlType === "mandatory";
        const activeChildren = children.filter((child) =>
          isMandatory ? true : isActive(index, child),
        );
        const noneSelected = !isMandatory && activeChildren.length === 0;

        return (
          <div key={`${node.name}-${relation.type}-${relationIndex}`} className="w-full">
            {!readOnly && title && (
              <div className="mb-2 flex items-center gap-2">
                <p className={cn(
                  "text-[0.65rem] font-bold uppercase tracking-widest",
                  noneSelected ? "text-destructive/70" : "text-muted-foreground",
                )}>
                  {title}
                </p>
                {noneSelected && hint && (
                  <p className="text-[0.65rem] text-destructive/60 italic">{hint}</p>
                )}
              </div>
            )}

            <div className={cn(
              "flex flex-wrap gap-2 rounded-lg p-1",
              noneSelected && !readOnly && "ring-1 ring-destructive/30 bg-destructive/5",
              depth > 0 && "gap-1.5",
            )}>
              {children.map((child) => {
                const active = isMandatory ? true : isActive(index, child);
                const label =
                  (child.attributes?.label as string | undefined) ??
                  labelMap?.[child.name] ??
                  child.name;
                if (isMandatory) {
                  return (
                    <span
                      key={child.name}
                      data-cy={`feature-${child.name}`}
                      className="inline-flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/5 px-3 py-1.5 text-sm font-medium text-foreground"
                    >
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                      {label}
                    </span>
                  );
                }

                const isOrDisabled =
                  relation.type === "OR" &&
                  active &&
                  children.filter((c) => isActive(index, c)).length === 1;

                return (
                  <button
                    key={child.name}
                    data-cy={`feature-${child.name}`}
                    type="button"
                    disabled={readOnly || isOrDisabled}
                    onClick={() => {
                      if (controlType === "radio") {
                        handleRadioChange(index, children, child);
                      } else {
                        if (!isOrDisabled) handleToggle(index, child);
                      }
                    }}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-lg border px-4 py-2 text-sm font-medium transition-colors",
                      depth > 0 && "px-3 py-1.5 text-xs",
                      active
                        ? "border-primary bg-primary text-primary-foreground shadow-sm"
                        : "border-border bg-card text-muted-foreground hover:border-primary/60 hover:bg-muted/50 hover:text-foreground",
                      (readOnly || isOrDisabled) && !active && "cursor-default opacity-40",
                    )}
                  >
                    {active && <Check className={cn("shrink-0", depth > 0 ? "h-3 w-3" : "h-3.5 w-3.5")} />}
                    {label}
                  </button>
                );
              })}
            </div>

            {activeChildren.map((child) => {
              if (!hasRelations(child)) return null;
              return (
                <div key={`sub-${child.name}`} className="mt-2 border-l-2 border-primary/25 pl-4 pt-1">
                  <FeatureNode
                    node={child}
                    index={index}
                    depth={depth + 1}
                    readOnly={readOnly}
                    labelMap={labelMap}
                  />
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
