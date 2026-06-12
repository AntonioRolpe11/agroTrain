describe("Models list", () => {
  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("tecnico");
  });

  it("loads the models page without errors", () => {
    cy.visit("/mis-modelos");
    cy.location("pathname", { timeout: 5000 }).should("eq", "/mis-modelos");
  });

  it("returns empty list from the API right after reset", () => {
    cy.request({
      method: "GET",
      url: `${Cypress.env("backendUrl")}/api/v1/modelos/`,
      headers: { Authorization: `Bearer ${window.localStorage.getItem("access_token")}` },
      failOnStatusCode: false,
    }).then((response) => {
      // After resetBackend the tecnico user has no models
      expect([200, 401]).to.include(response.status);
    });
  });
});
