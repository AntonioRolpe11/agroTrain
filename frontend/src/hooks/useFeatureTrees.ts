import { useContext } from "react";

import { FeatureTreesContext } from "@/contexts/FeatureTreesContext";

export function useFeatureTrees() {
  const ctx = useContext(FeatureTreesContext);
  if (!ctx) throw new Error("useFeatureTrees must be used within FeatureTreesProvider");
  return ctx;
}
