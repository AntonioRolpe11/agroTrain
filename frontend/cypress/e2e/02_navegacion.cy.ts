/**
 * Navegación general: landing, CTAs, navbar, página educativa y 404.
 * Recorre la app como un usuario autenticado moviéndose entre páginas.
 */
describe("Navegación de la plataforma", () => {
  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("tecnico");
    cy.visit("/");
    // Espera a que el refresh JWT se asiente antes de navegar de nuevo
    // (dos cy.visit seguidos sin asentar la sesión la pierden por rotación).
    cy.get('[data-cy="nav-logout"]', { timeout: 10000 }).should("be.visible");
  });

  it("muestra la landing y sus CTAs principales", () => {
    cy.contains("h1", "sensores virtuales").should("be.visible");
    cy.contains("a", "Crear sensor digital").should("have.attr", "href", "/creacion-sensor-digital");
    cy.contains("a", "Mis modelos").should("have.attr", "href", "/mis-modelos");
  });

  it("navega a la creación de sensor desde la landing", () => {
    cy.contains("a", "Crear sensor digital").click();
    cy.location("pathname").should("eq", "/creacion-sensor-digital");
    cy.contains("h1", "Creación de sensor digital").should("be.visible");
  });

  it("abre la página '¿Cómo funciona?'", () => {
    cy.contains("a", "Ver cómo funciona").click();
    cy.location("pathname").should("eq", "/como-funciona");
  });

  it("navega por la navbar entre las secciones principales", () => {
    cy.contains("header a", "Mis modelos").click();
    cy.location("pathname").should("eq", "/mis-modelos");
    cy.contains("header a", "Datos y entrenamiento").click();
    cy.location("pathname").should("eq", "/validacion-modelo");
    cy.contains("header a", "Inicio").click();
    cy.location("pathname").should("eq", "/");
  });

  it("muestra la página 404 en rutas desconocidas", () => {
    cy.visit("/ruta-que-no-existe");
    cy.contains("Página no encontrada", { timeout: 10000 }).should("be.visible");
  });
});
