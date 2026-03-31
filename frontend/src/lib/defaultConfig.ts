import type { ConfigState } from "@/types/config";

export const defaultConfig: ConfigState = {
  entrada: {
    sensores: {
      humedadSuelo: false,
      profundidadesHumedad: [],
      temperaturaAire: false,
      mcd: false,
      tasaBuenos: false,
      tasaSeveros: false,
    },
    datosTelemetria: {
      indices: [],
      cloudThreshold: 20,
    },
  },
  variableObjetivo: null,
  parcela: {
    nombre: "",
    especieCultivo: null,
    tipoSuelo: null,
    provinciaId: null,
    provinciaNombre: null,
    municipioId: null,
    municipioNombre: null,
    punto: null,
  },
  salidas: {
    visualizacionSerie: true,
    visualizacionIndicadores: true,
    exportacionResultados: true,
    sensorVirtualEnMapa: false,
  },
};
