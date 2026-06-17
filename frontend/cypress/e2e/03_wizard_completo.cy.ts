/**
 * Wizard del configurador completo (UVL → UI), los 4 pasos por navegador.
 *
 * Verifica el desbloqueo progresivo paso a paso y que, al validar la
 * configuración completa (is_full), la app navega a /validacion-modelo.
 * Las selecciones usan nombres de feature del UVL (data-cy="feature-<name>"),
 * no etiquetas en español, así el test sobrevive a cambios de etiqueta.
 */
describe("Wizard del configurador (4 pasos)", () => {
  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("tecnico");
  });

  it("desbloquea cada paso y valida la configuración completa", () => {
    cy.visit("/creacion-sensor-digital");
    cy.contains("h1", "Creación de sensor digital", { timeout: 15000 }).should("be.visible");

    // Paso 2 (sensores) aún bloqueado
    cy.contains("Parámetros de entrada").should("not.exist");

    // Paso 1 — Parcela
    cy.get('[data-cy="feature-RiegoDeficitario"]').click();
    cy.get('[data-cy="feature-Luvisoles"]').click();
    cy.get("#parcela-provincia option").should("have.length.greaterThan", 1);
    cy.get("#parcela-provincia option").eq(1).then((o) => cy.get("#parcela-provincia").select(String(o.val())));
    cy.get("#parcela-municipio option", { timeout: 10000 }).should("have.length.greaterThan", 1);
    cy.get("#parcela-municipio option").eq(1).then((o) => cy.get("#parcela-municipio").select(String(o.val())));
    cy.get('[data-cy="wizard-parcel-next"]').should("not.be.disabled").click();

    // Paso 2 — Sensores desbloqueado; telemetría aún no
    cy.contains("Parámetros de entrada").should("be.visible");
    cy.contains("Datos de telemetría").should("not.exist");
    cy.get('[data-cy="feature-DatoTB"]').click();
    cy.get('[data-cy="feature-HumedadSuelo"]').click();
    cy.get('[data-cy="feature-Hd35"]').click();
    cy.get('[data-cy="feature-DPV"]').click();
    cy.get('[data-cy="wizard-sensors-next"]').should("not.be.disabled").click();

    // Paso 3 — Telemetría desbloqueada
    cy.contains("Datos de telemetría").should("be.visible");
    cy.get('[data-cy="feature-NDVI"]').click();
    cy.get('[data-cy="wizard-telemetry-next"]').should("not.be.disabled").click();

    // Paso 4 — Objetivo + validar
    cy.contains("Variable objetivo").should("be.visible");
    cy.get('[data-cy="feature-TasaBuenos"]').click();
    cy.get('[data-cy="wizard-generate"]').should("not.be.disabled").click();

    // Validación completa OK → navega a Results
    cy.location("pathname", { timeout: 15000 }).should("eq", "/validacion-modelo");
    cy.contains("Resumen de la configuración").should("be.visible");
    cy.contains("Riego deficitario").should("be.visible");
  });

  it("el comando cy.completeWizard reutilizable llega a Results", () => {
    cy.completeWizard();
    cy.contains("Resumen de la configuración").should("be.visible");
  });
});
