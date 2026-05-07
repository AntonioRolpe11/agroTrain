import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowRight, Cpu, Droplets, Satellite, Sprout } from "lucide-react";
import heroImage from "@/assets/hero-olive.jpg";

const concepts = [
  {
    icon: Droplets,
    title: "Sensores físicos",
    description: "Humedad, dendrómetro y meteorología para caracterizar el estado de la parcela.",
    chipClass: "sensor-chip-physical",
  },
  {
    icon: Satellite,
    title: "Datos de telemetría",
    description: "Selección múltiple de NDVI, EVI, SAVI y NDWI con reglas por tratamiento y suelo.",
    chipClass: "sensor-chip-satellite",
  },
  {
    icon: Cpu,
    title: "Sensor virtual",
    description: "Configuración, validación y vista de resultados en un único flujo.",
    chipClass: "sensor-chip-virtual",
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
              TFG · Configurador generalista
            </div>
            <h1 className="text-4xl lg:text-5xl font-bold text-foreground leading-[1.1] mb-5">
              Generación de sensores virtuales con variabilidad controlada
            </h1>
            <p className="text-lg text-muted-foreground leading-relaxed mb-8 max-w-lg">
              Prototipo frontend saneado para crear sensores digitales en una sola pantalla, alineado con el alcance del TFG.
            </p>
            <div className="flex gap-3">
              <Button asChild size="lg" className="active:scale-[0.97] transition-transform">
                <Link to="/creacion-sensor-digital">
                  Crear sensor digital
                  <ArrowRight className="w-4 h-4 ml-1" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg" className="active:scale-[0.97] transition-transform">
                <Link to="/arquitectura">Ver arquitectura</Link>
              </Button>
            </div>
          </div>
        </div>
      </section>

      <section className="section-container py-20">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <h2 className="text-3xl font-bold mb-4">Enfoque de esta fase</h2>
          <p className="text-muted-foreground text-lg">
            Flujo unificado de creación de sensor digital. La ejecución real se integrará después con backend Python + Flamapy.
          </p>
        </div>
        <div className="grid md:grid-cols-3 gap-6">
          {concepts.map((c) => (
            <div key={c.title} className="config-block group hover:shadow-md transition-shadow duration-300 animate-reveal-up">
              <div className={`${c.chipClass} mb-4 w-fit`}>
                <c.icon className="w-4 h-4" />
                {c.title}
              </div>
              <p className="text-muted-foreground text-sm leading-relaxed">{c.description}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
