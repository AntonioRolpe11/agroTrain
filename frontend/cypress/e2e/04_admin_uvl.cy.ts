describe("Admin: UVL editor", () => {
  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("admin");
  });

  it("lists existing UVL versions via API", () => {
    cy.loginAs("admin").then(() => {
      cy.request({
        method: "POST",
        url: `${Cypress.env("backendUrl")}/api/v1/auth/login`,
        body: { email: Cypress.env("adminEmail"), password: Cypress.env("adminPassword") },
      }).then((login) => {
        cy.request({
          method: "GET",
          url: `${Cypress.env("backendUrl")}/api/v1/uvl/versions/`,
          headers: { Authorization: `Bearer ${(login.body as any).access}` },
        }).then((response) => {
          expect(response.status).to.eq(200);
          expect(response.body).to.be.an("array");
          expect(response.body.length).to.be.greaterThan(0);
          const active = response.body.filter((v: any) => v.is_active);
          expect(active.length).to.eq(1);
        });
      });
    });
  });

  it("loads the UVL editor admin page", () => {
    cy.visit("/uvl-editor");
    cy.location("pathname", { timeout: 8000 }).should("eq", "/uvl-editor");
  });
});
