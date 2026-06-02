describe("Admin: user CRUD via API", () => {
  beforeEach(() => {
    cy.resetBackend();
  });

  it("creates and deletes a tecnico user as admin", () => {
    cy.request({
      method: "POST",
      url: `${Cypress.env("backendUrl")}/api/v1/auth/login`,
      body: { email: Cypress.env("adminEmail"), password: Cypress.env("adminPassword") },
    }).then((login) => {
      const token = (login.body as any).access;
      const authHeader = { Authorization: `Bearer ${token}` };

      // Create
      cy.request({
        method: "POST",
        url: `${Cypress.env("backendUrl")}/api/v1/auth/users/`,
        headers: authHeader,
        body: { email: "cyp-user@test.local", nombre: "Cypress", role: "tecnico", password: "cypress123" },
      }).then((create) => {
        expect(create.status).to.eq(201);
        const id = (create.body as any).id;

        // Read back
        cy.request({
          method: "GET",
          url: `${Cypress.env("backendUrl")}/api/v1/auth/users/${id}/`,
          headers: authHeader,
        }).its("body.email").should("eq", "cyp-user@test.local");

        // Delete
        cy.request({
          method: "DELETE",
          url: `${Cypress.env("backendUrl")}/api/v1/auth/users/${id}/`,
          headers: authHeader,
        }).its("status").should("eq", 204);
      });
    });
  });

  it("denies user creation to a tecnico", () => {
    cy.request({
      method: "POST",
      url: `${Cypress.env("backendUrl")}/api/v1/auth/login`,
      body: { email: Cypress.env("tecnicoEmail"), password: Cypress.env("tecnicoPassword") },
    }).then((login) => {
      const token = (login.body as any).access;
      cy.request({
        method: "POST",
        url: `${Cypress.env("backendUrl")}/api/v1/auth/users/`,
        headers: { Authorization: `Bearer ${token}` },
        body: { email: "x@x.com", nombre: "X", role: "tecnico", password: "p1234567" },
        failOnStatusCode: false,
      }).its("status").should("eq", 403);
    });
  });
});
