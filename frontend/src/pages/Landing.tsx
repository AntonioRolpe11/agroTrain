import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowRight, BrainCircuit, Cpu, LayoutList, Satellite, Sprout } from "lucide-react";
import heroImage from "@/assets/hero-olive.jpg";

const features = [
  {
    icon: Sprout,
    title: "Configuración SPL",
    description:
      "Asistente de 4 pasos guiado por el modelo de características UVL. Flamapy valida cada decisión por satisfacibilidad BDD — tratamiento, suelo, sensores y variable objetivo.",
    chipClass: "sensor-chip-physical",
  },
  {
    icon: Satellite,
    title: "Datos",
    description:
      "Carga archivos CSV de sensores físicos. Extrae índices de vegetación NDVI, EVI, SAVI y NDWI de Sentinel-2 vía Google Earth Engine. Fusión automática en serie temporal diaria.",
    chipClass: "sensor-chip-satellite",
  },
  {
    icon: BrainCircuit,
    title: "Entrenamiento ML",
    description:
      "Entrena un modelo por variable objetivo. Algoritmo, ventana temporal y umbrales de calidad derivan del UVL — sin parámetros hardcodeados en Python.",
    chipClass: "sensor-chip-virtual",
  },
  {
    icon: Cpu,
    title: "Predicción",
    description:
      "Genera predicciones one-step-ahead sobre datos históricos reales. Historial de inferencias por modelo, con advertencias de calidad según umbrales definidos en el UVL.",
    chipClass: "sensor-chip-physical",
  },
];

export default function Landing() {
  return (
    <div>
      <section className="relative overflow-hidden">
        <div className="absolute inset-0">
          <img src={heroImage} alt="Olivar" className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-r from-background via-background/85 to-background/40" />
        </div>
        <div className="relative section-container py-24 lg:py-32">
          <div className="max-w-xl animate-reveal-up">
            <div className="sensor-chip-physical mb-4">
              <Sprout className="w-3.5 h-3.5" />
              Olivicultura de precisión
            </div>
            <h1 className="text-4xl lg:text-5xl font-bold text-foreground leading-[1.1] mb-5">
              Configura, entrena y predice con sensores virtuales
            </h1>
            <p className="text-lg text-muted-foreground leading-relaxed mb-8 max-w-lg">
              Esta plataforma ofrece la opción de configurar sensores digitales para parcelas de olivar, entrenar modelos ML con datos reales y generar predicciones de variables agronómicas.
            </p>
            <div className="flex gap-3">
              <Button asChild size="lg" className="active:scale-[0.97] transition-transform">
                <Link to="/creacion-sensor-digital">
                  Crear sensor digital
                  <ArrowRight className="w-4 h-4 ml-1" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg" className="active:scale-[0.97] transition-transform">
                <Link to="/mis-modelos">
                  <LayoutList className="w-4 h-4 mr-1" />
                  Mis modelos
                </Link>
              </Button>
            </div>
          </div>
        </div>
      </section>

      <section className="section-container py-20">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <h2 className="text-3xl font-bold mb-4">Flujo completo de extremo a extremo</h2>
          <p className="text-muted-foreground text-lg">
            Desde la selección de características hasta la predicción agronómica, todo parametrizado por el modelo de características UVL activo.
          </p>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((f, i) => (
            <div
              key={f.title}
              className="config-block group hover:shadow-md transition-shadow duration-300 animate-reveal-up relative"
            >
              <span className="absolute top-4 right-4 text-2xl font-bold text-muted-foreground/20 select-none">
                0{i + 1}
              </span>
              <div className={`${f.chipClass} mb-4 w-fit`}>
                <f.icon className="w-4 h-4" />
                {f.title}
              </div>
              <p className="text-muted-foreground text-sm leading-relaxed">{f.description}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
