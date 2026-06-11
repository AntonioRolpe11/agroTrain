describe("Wizard smoke", () => {
  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("tecnico"); // visits /login + persists the JWT on the app origin
  });

  it("lands on an authenticated page (not /login) after login", () => {
    cy.visit("/");
    cy.location("pathname", { timeout: 10000 }).should("not.equal", "/login");
  });

  it("opens the configurator route and renders the wizard", () => {
    cy.visit("/creacion-sensor-digital");
    cy.contains("h1", "Creación de sensor digital", { timeout: 10000 }).should(
      "be.visible",
    );
    // Parcel step (ParcelDataCard) is the first wizard block
    cy.get("#parcela-nombre", { timeout: 10000 }).should("exist");
  });
});
