import { createContext, useState, useEffect, type ReactNode } from "react";

import type { FeatureModelNode } from "@/types/api";
import { addFeatureSubtree, removeFeatureSubtree } from "@/utils/featureModel";

export interface FeatureTree {
  features: string[];
  [key: string]: unknown;
}

interface FeatureTreesContextValue {
  trees: FeatureTree[];
  setTrees: React.Dispatch<React.SetStateAction<FeatureTree[]>>;
  handleToggle: (index: number, feature: FeatureModelNode) => void;
  handleRadioChange: (index: number, alternativeGroup: FeatureModelNode[], feature: FeatureModelNode) => void;
  isActive: (index: number, feature: FeatureModelNode) => boolean;
  getProperty: <T>(index: number, property: string) => T;
  setProperty: (index: number, property: string, value: unknown) => void;
}

export const FeatureTreesContext = createContext<FeatureTreesContextValue | null>(null);

interface FeatureTreesProviderProps {
  children: ReactNode;
  initialTrees?: FeatureTree[];
}

export function FeatureTreesProvider({ children, initialTrees = [] }: FeatureTreesProviderProps) {
  const [trees, setTrees] = useState<FeatureTree[]>(initialTrees);

  useEffect(() => {
    setTrees(initialTrees);
  }, [initialTrees]);

  const addFeature = (index: number, feature: FeatureModelNode) => {
    setTrees((prev) => {
      const copy = [...prev];
      copy[index] = {
        ...copy[index],
        features: addFeatureSubtree(prev[index].features, feature),
      };
      return copy;
    });
  };

  const removeFeature = (index: number, feature: FeatureModelNode) => {
    setTrees((prev) => {
      const copy = [...prev];
      copy[index] = {
        ...copy[index],
        features: removeFeatureSubtree(prev[index].features, feature),
      };
      return copy;
    });
  };

  const handleToggle = (index: number, feature: FeatureModelNode) => {
    const currentFeatures = trees[index].features ?? [];
    if (currentFeatures.includes(feature.name)) {
      removeFeature(index, feature);
    } else {
      addFeature(index, feature);
    }
  };

  const handleRadioChange = (
    index: number,
    alternativeGroup: FeatureModelNode[],
    feature: FeatureModelNode,
  ) => {
    const currentFeatures = trees[index].features ?? [];
    if (currentFeatures.includes(feature.name)) {
      removeFeature(index, feature);
      return;
    }
    const activeFeature = alternativeGroup.find((f) => currentFeatures.includes(f.name));
    if (activeFeature) removeFeature(index, activeFeature);
    addFeature(index, feature);
  };

  const isActive = (index: number, feature: FeatureModelNode): boolean => {
    return trees[index]?.features?.includes(feature.name) ?? false;
  };

  const getProperty = <T,>(index: number, property: string): T => {
    return trees[index][property] as T;
  };

  const setProperty = (index: number, property: string, value: unknown) => {
    setTrees((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [property]: value };
      return copy;
    });
  };

  return (
    <FeatureTreesContext.Provider
      value={{ trees, setTrees, handleToggle, handleRadioChange, isActive, getProperty, setProperty }}
    >
      {children}
    </FeatureTreesContext.Provider>
  );
}
