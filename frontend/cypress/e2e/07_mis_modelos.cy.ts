/**
 * Página "Mis modelos": listado, acciones por fila y guardas de UI.
 * El modelo se crea como precondición vía API (rápido y determinista); la
 * página se ejercita por navegador.
 */
describe("Mis modelos", () => {
  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("tecnico");
    cy.on("window:confirm", () => true);
  });

  it("lista un modelo entrenado y permite ir a generar valor", () => {
    cy.trainModelViaApi(); // geo con punto → "Generar valor" habilitado
    cy.visit("/mis-modelos");

    cy.get('[data-cy="model-row"]', { timeout: 10000 }).should("have.length", 1).within(() => {
      cy.contains("RiegoDeficitario").should("be.visible");
      cy.get('[data-cy="model-download"]').should("be.visible");
    });

    cy.get('[data-cy="model-generar"]').click();
    cy.location("pathname", { timeout: 10000 }).should("match", /\/mis-modelos\/.+\/generar-valor$/);
  });

  it("borra un modelo con confirmación", () => {
    cy.trainModelViaApi();
    cy.visit("/mis-modelos");
    cy.get('[data-cy="model-row"]', { timeout: 10000 }).should("have.length", 1);
    cy.get('[data-cy="model-delete"]').click();
    cy.contains("No hay modelos guardados", { timeout: 10000 }).should("be.visible");
  });

  it("deshabilita 'Generar valor' para modelos sin ubicación guardada", () => {
    cy.trainModelViaApi({ geo: { nombre: "Sin punto E2E" } }); // sin geo.punto
    cy.visit("/mis-modelos");
    cy.get('[data-cy="model-row"]', { timeout: 10000 }).should("have.length", 1);
    cy.get('[data-cy="model-generar-disabled"]').should("be.disabled");
    cy.get('[data-cy="model-generar"]').should("not.exist");
  });
});
