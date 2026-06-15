import { Link } from "react-router-dom";
import {
  ArrowRight,
  BrainCircuit,
  Cpu,
  Layers,
  MapPin,
  Satellite,
  ShieldCheck,
  Sprout,
  Target,
} from "lucide-react";

import { Button } from "@/components/ui/button";

const steps = [
  {
    icon: Sprout,
    title: "1 · Parcela",
    description:
      "Eliges el tratamiento de riego, el tipo de suelo y un punto concreto del campo sobre el mapa. Ese punto —no una parcela cerrada— es el lugar donde quieres disponer del sensor digital.",
  },
  {
    icon: Layers,
    title: "2 · Sensores",
    description:
      "Indicas de qué sensores físicos tienes datos (dendrómetro, humedad del suelo, temperatura, riego, lluvia…). El asistente solo deja avanzar con combinaciones válidas.",
  },
  {
    icon: Satellite,
    title: "3 · Satélite",
    description:
      "Opcionalmente añades índices de vegetación (NDVI, EVI, SAVI, NDWI) que se extraen de Sentinel-2 para el punto elegido. Complementan a los sensores de campo.",
  },
  {
    icon: Target,
    title: "4 · Qué predecir",
    description:
      "Seleccionas la variable objetivo (MCD, Tasa de buenos o Tasa de severos). Con eso el sistema entrena un modelo a la medida de tu configuración.",
  },
];

const concepts = [
  {
    icon: Cpu,
    title: "¿Qué es un «sensor digital»?",
    description:
      "Un modelo que estima una variable agronómica allí donde no tienes un sensor físico. Aprende de tus datos históricos y, una vez entrenado, calcula el valor sin necesidad de instalar el sensor real, ahorrando costes.",
  },
  {
    icon: MapPin,
    title: "Eliges un punto, no una parcela",
    description:
      "Sobre el mapa marcas un punto del campo: la ubicación donde quieres simular el sensor. La cartografía solo te ayuda a situarlo; no seleccionas un recinto cerrado.",
  },
  {
    icon: ShieldCheck,
    title: "¿Por qué hay combinaciones que no se permiten?",
    description:
      "No todas las mezclas de tratamiento, suelo, sensores y objetivo tienen sentido agronómico o técnico. El asistente valida cada decisión y, si una combinación no es viable, te avisa y te indica qué falta para corregirla.",
  },
  {
    icon: BrainCircuit,
    title: "¿Qué hace «Generar valor»?",
    description:
      "Sobre un modelo ya entrenado, calcula el valor estimado de la variable para el día siguiente a partir de tus datos recientes. Devuelve un valor numérico de la variable, no una recomendación de riego.",
  },
];

export default function ComoFunciona() {
  return (
    <div>
      <section className="section-container py-16 lg:py-20">
        <div className="max-w-2xl">
          <div className="sensor-chip-physical mb-4">
            <Sprout className="h-3.5 w-3.5" />
            Cómo funciona
          </div>
          <h1 className="mb-5 text-3xl font-bold leading-tight text-foreground lg:text-4xl">
            De los datos de tu campo a una predicción agronómica
          </h1>
          <p className="text-lg leading-relaxed text-muted-foreground">
            AgroTrain te permite crear <strong>sensores digitales</strong> para el olivar: modelos que
            estiman variables agronómicas a partir de los datos que ya tienes, sin instalar nuevos
            sensores físicos. El proceso es un asistente guiado de cuatro pasos.
          </p>
        </div>
      </section>

      <section className="section-container pb-16">
        <h2 className="mb-6 text-2xl font-bold">El asistente, paso a paso</h2>
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {steps.map((s) => (
            <div key={s.title} className="config-block">
              <div className="sensor-chip-physical mb-4 w-fit">
                <s.icon className="h-4 w-4" />
                {s.title}
              </div>
              <p className="text-sm leading-relaxed text-muted-foreground">{s.description}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section-container pb-16">
        <h2 className="mb-6 text-2xl font-bold">Conceptos clave</h2>
        <div className="grid gap-6 md:grid-cols-2">
          {concepts.map((c) => (
            <div key={c.title} className="config-block">
              <div className="mb-3 flex items-center gap-2">
                <c.icon className="h-5 w-5 text-olive" />
                <h3 className="font-semibold">{c.title}</h3>
              </div>
              <p className="text-sm leading-relaxed text-muted-foreground">{c.description}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section-container pb-16">
        <div className="config-block">
          <h2 className="mb-3 text-xl font-bold">¿Cómo sé si el modelo acierta?</h2>
          <p className="mb-3 text-sm leading-relaxed text-muted-foreground">
            Cuando dispones del sensor físico de la variable que quieres predecir, puedes crear el
            modelo como <strong>sensor digital de validación</strong>. En ese modo la plataforma reserva
            una parte de los datos, compara lo previsto frente a lo real sobre datos que el modelo no ha
            visto y muestra las <strong>métricas de calidad (MAE, RMSE y R²)</strong> junto a la gráfica
            de real frente a predicho. Así compruebas la validez del modelo antes de fiarte de él.
          </p>
          <p className="text-sm leading-relaxed text-muted-foreground">
            Si solo quieres el predictor, lo creas como <strong>sensor digital</strong> operativo: se
            entrena con todos los datos —sin reservar conjunto de comparación, por lo que no genera
            métricas— y se usa para estimar la variable allí donde no tienes un sensor físico.
          </p>
        </div>
      </section>

      <section className="section-container pb-20">
        <div className="flex flex-wrap gap-3">
          <Button asChild size="lg" className="active:scale-[0.97] transition-transform">
            <Link to="/creacion-sensor-digital">
              Crear sensor digital
              <ArrowRight className="ml-1 h-4 w-4" />
            </Link>
          </Button>
          <Button asChild variant="outline" size="lg" className="active:scale-[0.97] transition-transform">
            <Link to="/mis-modelos">Mis modelos</Link>
          </Button>
        </div>
      </section>
    </div>
  );
}
