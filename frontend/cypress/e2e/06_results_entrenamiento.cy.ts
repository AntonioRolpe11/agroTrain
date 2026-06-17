/**
 * Flujo pesado 1 — Results: ingesta de CSV → fusión → entrenamiento real.
 *
 * Tras completar el wizard, sube por la UI un dendrómetro sintético (la app
 * calcula TasaBuenos con dendroCalc), los sensores de humedad y DPV, y un CSV
 * de telemetría propio (evita GEE de forma determinista). Fusiona, lanza el
 * entrenamiento real (sklearn, CSV pequeño) y espera a que la UI muestre el
 * estado "completado" con sus métricas.
 */
import { buildDendrometerCsv, buildDailySensorCsv, buildTelemetryCsv } from "../support/fixtures";

describe("Results: ingesta → fusión → entrenamiento", () => {
  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("tecnico");
  });

  it("entrena un modelo de validación end-to-end por la UI", () => {
    cy.completeWizard(); // RiegoDeficitario + Luvisoles + DatoTB/Hd35/DPV + NDVI + TasaBuenos
    cy.contains("Resumen de la configuración", { timeout: 15000 }).should("be.visible");

    // 1. Subir sensores (dendrómetro sub-diario + humedad + dpv)
    cy.uploadSensorCard("Dendrómetro", buildDendrometerCsv(90), "dendro.csv", "timestamp", "valor");
    cy.uploadSensorCard("35 cm", buildDailySensorCsv(90, "2023-01-01", { base: 30, amp: 4 }), "hd35.csv", "fecha", "valor");
    cy.uploadSensorCard("Déficit de presión de vapor", buildDailySensorCsv(90, "2023-01-01", { base: 1.2, amp: 0.4 }), "dpv.csv", "fecha", "valor");

    // 2. Telemetría propia por CSV (date;NDVI) — sustituye la extracción GEE
    cy.get("#telemetry-csv-upload").selectFile(
      { contents: Cypress.Buffer.from(buildTelemetryCsv(["NDVI"], 90, "2023-01-01")), fileName: "telemetria.csv" },
      { force: true },
    );

    // 3. Fusionar
    cy.get('[data-cy="results-fuse"]', { timeout: 10000 }).should("not.be.disabled").click();
    cy.contains("Fusión de datos").parent().should("exist");
    cy.contains(/filas/i, { timeout: 10000 });

    // 4. Entrenar (sensor de validación → genera métricas)
    cy.get('[data-cy="sensor-type-validacion"]').check({ force: true });
    cy.get('[data-cy="results-train"]', { timeout: 10000 }).should("not.be.disabled").click();

    // 5. Esperar a "completado" (entrenamiento real) y comprobar métricas
    cy.get('[data-cy="results-training-completed"]', { timeout: 180000 }).should("be.visible");
    cy.get('[data-cy="results-metrics"]').should("be.visible").and("contain", "TasaBuenos");
    cy.get('[data-cy="results-download-model"]').should("be.visible");

    // El modelo queda guardado en el servidor
    cy.visit("/mis-modelos");
    cy.get('[data-cy="model-row"]', { timeout: 10000 }).should("have.length", 1);
  });
});
