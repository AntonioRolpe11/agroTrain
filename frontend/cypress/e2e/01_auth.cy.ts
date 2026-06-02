describe("Auth flow", () => {
  beforeEach(() => {
    cy.resetBackend();
  });

  it("redirects unauthenticated users to /login when visiting a protected page", () => {
    cy.visit("/");
    cy.url().should("include", "/login");
  });

  it("logs in via the form and lands on the home page", () => {
    cy.visit("/login");
    cy.get("#email").type(Cypress.env("tecnicoEmail"));
    cy.get("#password").type(Cypress.env("tecnicoPassword"));
    cy.contains("button", "Entrar").click();
    cy.url({ timeout: 10000 }).should("not.include", "/login");
  });

  it("rejects invalid credentials with an error message", () => {
    cy.visit("/login");
    cy.get("#email").type("nope@example.com");
    cy.get("#password").type("wrongpwd9");
    cy.contains("button", "Entrar").click();
    cy.contains(/Credenciales|Error/i, { timeout: 5000 }).should("be.visible");
  });
});
