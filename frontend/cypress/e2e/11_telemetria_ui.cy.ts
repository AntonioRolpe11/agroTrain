/**
 * UI de telemetría con GEE simulado (cy.intercept).
 *
 * Google Earth Engine no está disponible en el entorno de test, así que se
 * intercepta POST /telemetry/extract con un fixture. Se entrena (vía API) un
 * modelo que SÍ usa NDVI y se conduce GenerarValorModelo: subir dendrómetro →
 * "Extraer telemetría" (stub) → ver la vista previa → fusionar → generar valor.
 */
import { buildDendrometerCsv } from "../support/fixtures";

function fusedWithNdvi(rows: number, startISO = "2022-01-01"): string {
  const lines = ["date;TasaBuenos;NDVI"];
  const start = new Date(`${startISO}T00:00:00Z`);
  for (let i = 0; i < rows; i++) {
    const d = new Date(start.getTime() + i * 86400000).toISOString().slice(0, 10);
    const tb = 0.55 + 0.2 * Math.sin(i / 9);
    const ndvi = 0.45 + 0.2 * Math.sin(i / 7);
    lines.push(`${d};${tb.toFixed(4)};${ndvi.toFixed(4)}`);
  }
  return lines.join("\n");
}

describe("Telemetría GEE (simulada) en inferencia", () => {
  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("tecnico");
    cy.on("window:confirm", () => true);
    cy.intercept("POST", "**/api/v1/telemetry/extract", { fixture: "telemetry-extract.json" }).as("extract");
  });

  it("extrae telemetría (stub), la previsualiza y genera un valor", () => {
    cy.trainModelViaApi({
      features: ["RiegoDeficitario", "Luvisoles", "NDVI", "TasaBuenos"],
      csv: fusedWithNdvi(180),
    }).then((modelId) => {
      cy.visit(`/mis-modelos/${modelId}/generar-valor`);
    });

    cy.contains("h1", "Generar valor", { timeout: 15000 }).should("be.visible");

    // Sensor histórico (dendrómetro → TasaBuenos)
    cy.uploadSensorCard("Dendrómetro", buildDendrometerCsv(40), "dendro.csv", "timestamp", "valor");

    // Extraer telemetría → la llamada GEE queda interceptada por el fixture
    cy.get('[data-cy="gv-extract-telemetry"]', { timeout: 10000 }).should("not.be.disabled").click();
    cy.wait("@extract");
    cy.contains("fechas extraídas", { timeout: 10000 }).should("be.visible");
    cy.contains("Vista previa").should("be.visible");
    cy.contains("NDVI").should("be.visible");

    // Fusionar y generar valor con telemetría incluida
    cy.get('[data-cy="gv-fuse"]').should("not.be.disabled").click();
    cy.contains(/filas fusionadas/i, { timeout: 10000 }).should("be.visible");
    cy.get('[data-cy="gv-predict"]').should("not.be.disabled").click();
    cy.get('[data-cy="gv-prediction-result"]', { timeout: 20000 }).should("be.visible").and("contain", "TasaBuenos");
  });
});
