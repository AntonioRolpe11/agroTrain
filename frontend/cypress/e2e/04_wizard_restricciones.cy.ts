/**
 * Núcleo SPL: las restricciones del UVL se aplican en la UI del wizard.
 *
 * Con `RiegoDeficitario` el UVL exige `(Hd35|Hd45|Hd55) & DPV` (paso sensores)
 * y `Luvisoles` exige `(NDVI|EVI)` (paso telemetría). El wizard debe mostrar
 * avisos ámbar (ConstraintHints) y mantener "Listo" deshabilitado hasta que se
 * satisfagan, sin ningún nombre de feature hardcodeado en el código de la app.
 */
describe("Restricciones del configurador (SPL)", () => {
  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("tecnico");
    cy.visit("/creacion-sensor-digital");

    // Parcela con tratamiento + suelo exigentes
    cy.get('[data-cy="feature-RiegoDeficitario"]', { timeout: 15000 }).click();
    cy.get('[data-cy="feature-Luvisoles"]').click();
    cy.get("#parcela-provincia option").should("have.length.greaterThan", 1);
    cy.get("#parcela-provincia option").eq(1).then((o) => cy.get("#parcela-provincia").select(String(o.val())));
    cy.get("#parcela-municipio option", { timeout: 10000 }).should("have.length.greaterThan", 1);
    cy.get("#parcela-municipio option").eq(1).then((o) => cy.get("#parcela-municipio").select(String(o.val())));
    cy.get('[data-cy="wizard-parcel-next"]').should("not.be.disabled").click();
  });

  it("bloquea sensores hasta satisfacer las restricciones del tratamiento", () => {
    // El tratamiento exige sensores → aviso ámbar + botón bloqueado
    cy.get('[data-cy="constraint-hint"]').should("have.length.greaterThan", 0);
    cy.get('[data-cy="wizard-sensors-next"]').should("be.disabled");

    // Satisfacemos las restricciones (DatoTB + Hd35 + DPV)
    cy.get('[data-cy="feature-DatoTB"]').click();
    cy.get('[data-cy="feature-HumedadSuelo"]').click();
    cy.get('[data-cy="feature-Hd35"]').click();
    cy.get('[data-cy="feature-DPV"]').click();

    // Avisos desaparecen y el botón se habilita
    cy.get('[data-cy="constraint-hint"]').should("not.exist");
    cy.get('[data-cy="wizard-sensors-next"]').should("not.be.disabled").click();

    // Paso telemetría: Luvisoles exige NDVI|EVI
    cy.get('[data-cy="constraint-hint"]').should("have.length.greaterThan", 0);
    cy.get('[data-cy="wizard-telemetry-next"]').should("be.disabled");
    cy.get('[data-cy="feature-NDVI"]').click();
    cy.get('[data-cy="constraint-hint"]').should("not.exist");
    cy.get('[data-cy="wizard-telemetry-next"]').should("not.be.disabled");
  });
});
