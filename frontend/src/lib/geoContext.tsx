import { createContext, useState, type ReactNode } from "react";

export interface GeoData {
  nombre: string;
  provinciaId: string | null;
  provinciaNombre: string | null;
  municipioId: string | null;
  municipioNombre: string | null;
  punto: { lat: number; lng: number } | null;
  cloudThreshold: number;
  startDate: string;
  endDate: string;
}

export const defaultGeoData: GeoData = {
  nombre: "",
  provinciaId: null,
  provinciaNombre: null,
  municipioId: null,
  municipioNombre: null,
  punto: null,
  cloudThreshold: 20,
  startDate: "",
  endDate: "",
};

interface GeoContextValue {
  geo: GeoData;
  setGeo: React.Dispatch<React.SetStateAction<GeoData>>;
  patchGeo: (patch: Partial<GeoData>) => void;
  resetGeo: () => void;
}

export const GeoContext = createContext<GeoContextValue | null>(null);

export function GeoProvider({ children }: { children: ReactNode }) {
  const [geo, setGeo] = useState<GeoData>(defaultGeoData);

  const patchGeo = (patch: Partial<GeoData>) =>
    setGeo((prev) => ({ ...prev, ...patch }));

  const resetGeo = () => setGeo(defaultGeoData);

  return (
    <GeoContext.Provider value={{ geo, setGeo, patchGeo, resetGeo }}>
      {children}
    </GeoContext.Provider>
  );
}
