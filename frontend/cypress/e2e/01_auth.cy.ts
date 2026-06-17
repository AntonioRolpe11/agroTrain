/**
 * Authentication + route guards, driven through the real UI.
 *
 * Covers: unauthenticated redirect, JWT login form (valid/invalid), session
 * persistence across reload, logout, and the admin-only route guards
 * (RequireAuth → /login, RequireAdmin → /).
 */
describe("Autenticación y guards de ruta", () => {
  beforeEach(() => {
    cy.resetBackend();
  });

  it("redirige al login cuando no hay sesión", () => {
    cy.visit("/");
    cy.location("pathname", { timeout: 10000 }).should("eq", "/login");
  });

  it("rechaza credenciales inválidas con un mensaje de error", () => {
    cy.visit("/login");
    cy.get("#email").type("admin@test.local");
    cy.get("#password").type("contraseña-incorrecta");
    cy.get('[data-cy="login-submit"]').click();
    cy.get('[data-cy="login-error"]', { timeout: 10000 }).should("be.visible");
    cy.location("pathname").should("eq", "/login");
  });

  it("inicia sesión con credenciales válidas y entra en la app", () => {
    cy.visit("/login");
    cy.get("#email").type(Cypress.env("tecnicoEmail"));
    cy.get("#password").type(Cypress.env("tecnicoPassword"));
    cy.get('[data-cy="login-submit"]').click();
    cy.location("pathname", { timeout: 10000 }).should("eq", "/");
    cy.get('[data-cy="nav-logout"]').should("be.visible");
  });

  it("mantiene la sesión tras recargar la página", () => {
    cy.loginAs("tecnico");
    cy.visit("/mis-modelos");
    cy.location("pathname").should("eq", "/mis-modelos");
    cy.reload();
    cy.location("pathname", { timeout: 10000 }).should("eq", "/mis-modelos");
    cy.get('[data-cy="nav-logout"]').should("be.visible");
  });

  it("cierra sesión y bloquea el acceso a rutas protegidas", () => {
    cy.loginAs("tecnico");
    cy.visit("/");
    cy.get('[data-cy="nav-logout"]', { timeout: 10000 }).click();
    cy.location("pathname", { timeout: 10000 }).should("eq", "/login");
    cy.visit("/mis-modelos");
    cy.location("pathname", { timeout: 10000 }).should("eq", "/login");
  });

  it("un técnico no puede acceder a rutas de administrador", () => {
    cy.loginAs("tecnico");
    cy.visit("/usuarios");
    cy.location("pathname", { timeout: 10000 }).should("eq", "/");
    cy.visit("/uvl-editor");
    cy.location("pathname", { timeout: 10000 }).should("eq", "/");
    // El técnico tampoco ve los enlaces de administración en la navbar.
    cy.get('[data-cy="nav-link-usuarios"]').should("not.exist");
    cy.get('[data-cy="nav-link-uvl"]').should("not.exist");
  });

  it("un administrador sí accede a las rutas de administrador", () => {
    cy.loginAs("admin");
    cy.visit("/");
    cy.get('[data-cy="nav-link-usuarios"]', { timeout: 10000 }).should("be.visible");
    cy.visit("/usuarios");
    cy.location("pathname").should("eq", "/usuarios");
    cy.contains("h1", "Gestión de usuarios").should("be.visible");
  });
});
