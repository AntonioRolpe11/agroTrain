export type ProfundidadHumedad =
  | "Hd05"
  | "Hd15"
  | "Hd25"
  | "Hd35"
  | "Hd45"
  | "Hd55"
  | "Hd65"
  | "Hd75";

export type VariableObjetivo = "TasaBuenos" | "TasaSeveros" | "MCD";
export type TelemetryIndex = "NDVI" | "EVI" | "SAVI" | "NDWI";
export type EspecieCultivo =
  | "Olivo"
  | "Almendro"
  | "Vid"
  | "Naranjo"
  | "Limonero"
  | "Mandarino"
  | "Melocotonero"
  | "Nectarino"
  | "Ciruelo"
  | "Albaricoquero";
export type TipoSuelo =
  | "CampinaArcillosa"
  | "LomasCalizasAlbariza"
  | "VegaAluvial"
  | "PiedemonteSierra"
  | "MarismasSalinas";

export interface ParcelPoint {
  lat: number;
  lng: number;
}

export type ParcelBoundingBox = [number, number, number, number];
export type ParcelPosition = [number, number];

export interface ParcelaConfig {
  nombre: string;
  especieCultivo: EspecieCultivo | null;
  tipoSuelo: TipoSuelo | null;
  provinciaId: string | null;
  provinciaNombre: string | null;
  municipioId: string | null;
  municipioNombre: string | null;
  punto: ParcelPoint | null;
}

export interface SalidasConfig {
  visualizacionSerie: boolean;
  visualizacionIndicadores: boolean;
  exportacionResultados: boolean;
  sensorVirtualEnMapa: boolean;
}

export interface ConfigState {
  entrada: {
    sensores: {
      humedadSuelo: boolean;
      profundidadesHumedad: ProfundidadHumedad[];
      temperaturaAire: boolean;
      mcd: boolean;
      tasaBuenos: boolean;
      tasaSeveros: boolean;
      // Dendrometro siempre obligatorio — no se modela como booleano
    };
    datosTelemetria: {
      indices: TelemetryIndex[];
      cloudThreshold: number;
    };
  };
  variableObjetivo: VariableObjetivo | null;
  parcela: ParcelaConfig;
  salidas: SalidasConfig;
}
