describe("Configuracion CRUD via API", () => {
  beforeEach(() => {
    cy.resetBackend();
  });

  it("creates, lists and deletes a configuracion as tecnico", () => {
    cy.request({
      method: "POST",
      url: `${Cypress.env("backendUrl")}/api/v1/auth/login`,
      body: { email: Cypress.env("tecnicoEmail"), password: Cypress.env("tecnicoPassword") },
    }).then((login) => {
      const token = (login.body as any).access;
      const authHeader = { Authorization: `Bearer ${token}` };

      cy.request({
        method: "POST",
        url: `${Cypress.env("backendUrl")}/api/v1/configurator/configuraciones/`,
        headers: authHeader,
        body: { nombre: "Mi parcela", features: ["RiegoControl"], geo: { lat: 37, lng: -5 } },
      }).then((create) => {
        expect(create.status).to.eq(201);
        const id = (create.body as any).id;

        cy.request({
          method: "GET",
          url: `${Cypress.env("backendUrl")}/api/v1/configurator/configuraciones/`,
          headers: authHeader,
        }).its("body").should("have.length.greaterThan", 0);

        cy.request({
          method: "DELETE",
          url: `${Cypress.env("backendUrl")}/api/v1/configurator/configuraciones/${id}/`,
          headers: authHeader,
        }).its("status").should("eq", 204);
      });
    });
  });
});
