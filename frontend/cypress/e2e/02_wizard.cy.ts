describe("Wizard step-by-step", () => {
  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("tecnico");
    cy.visit("/");
  });

  it("loads the configurator UI after login", () => {
    // Smoke test: the wizard or landing page should render successfully
    cy.location("pathname", { timeout: 10000 }).should("not.equal", "/login");
  });

  it("allows opening the configurator route", () => {
    cy.visit("/creacion-sensor-digital");
    cy.contains(/configurador|wizard|parcela|sensor/i, { timeout: 10000 }).should("exist");
  });
});
