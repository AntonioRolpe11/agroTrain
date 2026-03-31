import { useContext } from "react";
import { GeoContext } from "@/lib/geoContext";

export function useGeo() {
  const ctx = useContext(GeoContext);
  if (!ctx) throw new Error("useGeo must be used inside GeoProvider");
  return ctx;
}
