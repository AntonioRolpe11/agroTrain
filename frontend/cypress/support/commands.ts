/// <reference types="cypress" />

declare global {
  namespace Cypress {
    interface Chainable {
      /** Flush DB + reseed UVL via Django mgmt command, then return credentials. */
      resetBackend(opts?: { uvl?: string }): Chainable<TestState>;
      /** Persist a JWT login token into localStorage, skipping the UI form. */
      loginAs(role: "admin" | "tecnico"): Chainable<void>;
    }
  }
}

export interface TestState {
  admin: { email: string; password: string; id: number };
  tecnico: { email: string; password: string; id: number };
  uvl_version_id: number;
  uvl_path: string;
}

Cypress.Commands.add("resetBackend", (opts = {}) => {
  return cy.task<TestState>("resetBackend", opts);
});

Cypress.Commands.add("loginAs", (role: "admin" | "tecnico") => {
  const email = role === "admin" ? Cypress.env("adminEmail") : Cypress.env("tecnicoEmail");
  const password = role === "admin" ? Cypress.env("adminPassword") : Cypress.env("tecnicoPassword");
  cy.request("POST", `${Cypress.env("backendUrl")}/api/v1/auth/login`, {
    email,
    password,
  }).then((response) => {
    expect(response.status).to.eq(200);
    const { access, refresh } = response.body as { access: string; refresh: string };
    cy.window().then((win) => {
      win.localStorage.setItem("access_token", access);
      win.localStorage.setItem("refresh_token", refresh);
    });
  });
});

export {};
