/**
 * Flujo pesado 2 — GenerarValorModelo: inferencia one-step-ahead por la UI.
 *
 * El modelo (sin telemetría, con punto) se entrena vía API como precondición.
 * Después se conduce la página por navegador: subir dendrómetro histórico →
 * fusionar → generar valor → ver el valor y el histórico → borrar la predicción.
 */
import { buildDendrometerCsv } from "../support/fixtures";

describe("Inferencia: generar valor", () => {
  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("tecnico");
    cy.on("window:confirm", () => true);
  });

  it("genera un valor, lo muestra y lo gestiona en el histórico", () => {
    cy.trainModelViaApi().then((modelId) => {
      cy.visit(`/mis-modelos/${modelId}/generar-valor`);
    });

    cy.contains("h1", "Generar valor", { timeout: 15000 }).should("be.visible");

    // 1. Histórico de dendrómetro → la app calcula TasaBuenos
    cy.uploadSensorCard("Dendrómetro", buildDendrometerCsv(40), "dendro.csv", "timestamp", "valor");

    // (modelo sin telemetría: el paso GEE se omite)
    cy.contains("El modelo no usa telemetría").should("be.visible");

    // 2. Fusionar
    cy.get('[data-cy="gv-fuse"]', { timeout: 10000 }).should("not.be.disabled").click();
    cy.contains(/filas fusionadas/i, { timeout: 10000 }).should("be.visible");

    // 3. Generar valor
    cy.get('[data-cy="gv-predict"]').should("not.be.disabled").click();
    cy.get('[data-cy="gv-prediction-result"]', { timeout: 20000 }).should("be.visible").and("contain", "TasaBuenos");

    // 4. El histórico registra la predicción
    cy.get('[data-cy="gv-history-item"]', { timeout: 10000 }).should("have.length", 1);

    // 5. Borrar la predicción
    cy.get('[data-cy="gv-delete-prediction"]').click();
    cy.contains("Aún no hay predicciones guardadas", { timeout: 10000 }).should("be.visible");
  });
});
