/**
 * Editor de versiones UVL (solo admin), conducido por la UI:
 * listar, bifurcar (crear desde una existente), guardar, activar (con su modal
 * de impacto) y borrar una versión no activa.
 */
describe("Editor de versiones UVL", () => {
  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("admin");
    cy.on("window:confirm", () => true);
    cy.visit("/uvl-editor");
  });

  it("lista la versión activa sembrada por el reset", () => {
    cy.get('[data-cy="uvl-version-card"]', { timeout: 10000 }).should("have.length", 1);
    cy.get('[data-cy="uvl-version-card"][data-cy-active="true"]').should("have.length", 1);
  });

  it("bifurca, guarda y activa una nueva versión", () => {
    // Seleccionar la versión activa y bifurcarla
    cy.get('[data-cy="uvl-version-card"]', { timeout: 10000 }).first().click();
    // Esperar a que el árbol de la versión cargue (fork necesita versionDetail.tree)
    cy.contains("Tratamientos", { timeout: 10000 }).should("be.visible");
    cy.get('[data-cy="uvl-fork"]').click();
    // El formulario de creación debe mostrar el árbol editable (no el placeholder)
    cy.get('[data-cy="uvl-draft-name"]', { timeout: 10000 }).should("be.visible");

    // Nombrar y guardar la nueva versión
    cy.get('[data-cy="uvl-draft-name"]').clear().type("Versión E2E");
    cy.get('[data-cy="uvl-save"]').click();

    // Ahora hay 2 versiones; la nueva no está activa
    cy.get('[data-cy="uvl-version-card"]', { timeout: 10000 }).should("have.length", 2);

    // Activar la nueva (botón → modal de impacto → confirmar)
    cy.get('[data-cy="uvl-activate"]', { timeout: 10000 }).click();
    cy.get('[data-cy="uvl-activate-confirm"]', { timeout: 10000 }).should("not.be.disabled").click();

    // La nueva versión queda activa
    cy.contains('[data-cy="uvl-version-card"]', "Versión E2E")
      .should("have.attr", "data-cy-active", "true");
  });

  it("borra una versión no activa", () => {
    // Crear una versión extra para tener una no activa que borrar
    cy.get('[data-cy="uvl-version-card"]', { timeout: 10000 }).first().click();
    // Esperar a que el árbol de la versión cargue (fork necesita versionDetail.tree)
    cy.contains("Tratamientos", { timeout: 10000 }).should("be.visible");
    cy.get('[data-cy="uvl-fork"]').click();
    // El formulario de creación debe mostrar el árbol editable (no el placeholder)
    cy.get('[data-cy="uvl-draft-name"]', { timeout: 10000 }).should("be.visible");
    cy.get('[data-cy="uvl-draft-name"]').clear().type("Borrame E2E");
    cy.get('[data-cy="uvl-save"]').click();
    cy.get('[data-cy="uvl-version-card"]', { timeout: 10000 }).should("have.length", 2);

    cy.contains('[data-cy="uvl-version-card"]', "Borrame E2E")
      .find('[data-cy="uvl-delete-version"]')
      .click({ force: true });

    cy.get('[data-cy="uvl-version-card"]', { timeout: 10000 }).should("have.length", 1);
  });
});
