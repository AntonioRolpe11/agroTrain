/**
 * Gestión de usuarios (solo admin), conducida por la UI: crear, editar,
 * activar/desactivar, borrar y auto-protección (no operar sobre uno mismo).
 */
describe("Administración de usuarios", () => {
  const NEW_EMAIL = "nuevo@test.local";

  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("admin");
    cy.on("window:confirm", () => true);
    cy.visit("/usuarios");
    cy.contains("h1", "Gestión de usuarios", { timeout: 10000 }).should("be.visible");
  });

  function createUser() {
    cy.get('[data-cy="users-new"]').click();
    cy.get('[data-cy="users-form"]').within(() => {
      cy.get("#nu-nombre").type("Usuario Nuevo");
      cy.get("#nu-email").type(NEW_EMAIL);
      cy.get("#nu-password").type("clave-segura-9");
      cy.get('[data-cy="users-submit"]').click();
    });
    cy.get(`[data-cy="user-row"][data-cy-email="${NEW_EMAIL}"]`, { timeout: 10000 }).should("exist");
  }

  it("crea un usuario nuevo", () => {
    createUser();
    cy.get(`[data-cy="user-row"][data-cy-email="${NEW_EMAIL}"]`).should("contain", "Usuario Nuevo");
  });

  it("edita el nombre de un usuario", () => {
    createUser();
    cy.get(`[data-cy="user-row"][data-cy-email="${NEW_EMAIL}"]`).find('[data-cy="user-edit"]').click();
    cy.get('[data-cy="users-form"]').within(() => {
      cy.get("#nu-nombre").clear().type("Nombre Editado");
      cy.get('[data-cy="users-submit"]').click();
    });
    cy.get(`[data-cy="user-row"][data-cy-email="${NEW_EMAIL}"]`, { timeout: 10000 }).should("contain", "Nombre Editado");
  });

  it("activa/desactiva un usuario", () => {
    createUser();
    cy.get(`[data-cy="user-row"][data-cy-email="${NEW_EMAIL}"]`)
      .find('[data-cy="user-toggle"]')
      .should("have.attr", "title", "Desactivar")
      .click();
    cy.get(`[data-cy="user-row"][data-cy-email="${NEW_EMAIL}"]`)
      .find('[data-cy="user-toggle"]')
      .should("have.attr", "title", "Activar");
  });

  it("borra un usuario", () => {
    createUser();
    cy.get(`[data-cy="user-row"][data-cy-email="${NEW_EMAIL}"]`).find('[data-cy="user-delete"]').click();
    cy.get(`[data-cy="user-row"][data-cy-email="${NEW_EMAIL}"]`).should("not.exist");
  });

  it("impide al admin borrarse o desactivarse a sí mismo", () => {
    const self = Cypress.env("adminEmail");
    cy.get(`[data-cy="user-row"][data-cy-email="${self}"]`).find('[data-cy="user-delete"]').should("be.disabled");
    cy.get(`[data-cy="user-row"][data-cy-email="${self}"]`).find('[data-cy="user-toggle"]').should("be.disabled");
  });
});
