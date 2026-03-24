import { BarChart3, Cpu, Database, GitBranch, Settings } from "lucide-react";

const flowSteps = [
  {
    icon: Database,
    title: "Entrada",
    desc: "Selección de parcela, sensores físicos, telemetría Sentinel-2 y variable objetivo según el modelo UVL.",
    color: "bg-sensor-green/15 text-sensor-green",
  },
  {
    icon: GitBranch,
    title: "Feature Model (UVL)",
    desc: "Definición de variabilidad y restricciones del configurador de sensores virtuales.",
    color: "bg-satellite-amber/15 text-satellite-amber",
  },
  {
    icon: Settings,
    title: "Validación",
    desc: "Comprobación de configuraciones válidas en base a restricciones declarativas.",
    color: "bg-primary/15 text-olive",
  },
  {
    icon: Cpu,
    title: "Ejecución backend",
    desc: "FastAPI + Flamapy para evaluación del UVL y validación coherente con el configurador.",
    color: "bg-data-blue/15 text-data-blue",
  },
  {
    icon: BarChart3,
    title: "Salidas",
    desc: "Serie, indicadores y exportación son obligatorias; el mapa se activa cuando aplica.",
    color: "bg-virtual-teal/15 text-virtual-teal",
  },
];

export default function Architecture() {
  return (
    <div className="section-container py-10">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-2 animate-reveal-up">Arquitectura del prototipo</h1>
        <p className="text-muted-foreground mb-10 animate-reveal-up" style={{ animationDelay: "60ms" }}>
          Estado actual: frontend y backend alineados con el UVL del TFG, incluyendo validación y análisis con Flamapy.
        </p>

        <div className="space-y-0 mb-12">
          {flowSteps.map((step, i) => (
            <div key={step.title} className="animate-reveal-up" style={{ animationDelay: `${100 + i * 80}ms` }}>
              <div className="flex items-start gap-4">
                <div className="flex flex-col items-center">
                  <div className={`w-12 h-12 rounded-xl ${step.color} flex items-center justify-center shrink-0`}>
                    <step.icon className="w-6 h-6" />
                  </div>
                  {i < flowSteps.length - 1 && <div className="w-px h-8 bg-border my-1" />}
                </div>
                <div className="pt-1 pb-4">
                  <h3 className="font-semibold text-sm">{step.title}</h3>
                  <p className="text-sm text-muted-foreground mt-1 leading-relaxed max-w-lg">{step.desc}</p>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="config-block animate-reveal-up" style={{ animationDelay: "520ms" }}>
          <h2 className="text-lg font-semibold mb-4">Modelo UVL objetivo</h2>
          <p className="text-sm text-muted-foreground mb-4 leading-relaxed">
            El configurador refleja la variabilidad real del UVL: Entrada y Salidas son mandatory; dentro de Salidas,
            serie, indicadores y exportación también son obligatorias, mientras que el mapa sigue siendo opcional.
          </p>
          <div className="bg-muted/50 rounded-lg p-5 font-mono text-xs leading-relaxed">
            <div className="text-olive font-semibold mb-2">Entrada</div>
            <div className="ml-4 space-y-1">
              <div>├── DatosParcela (Cultivo | TipoSuelo)</div>
              <div>├── ParametrosEntrada</div>
              <div className="ml-6">├── Dendrometro (opcional: DatoMCD, DatoTB, DatoTS)</div>
              <div className="ml-6">└── HumedadSuelo (Hd05–Hd75) · TemperaturaAire</div>
              <div>├── DatosTelemetria (NDVI, EVI, SAVI, NDWI · Nubes)</div>
              <div>└── VariableObjetivo (TasaBuenos | TasaSeveros | MCD)</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
