/// <reference types="cypress" />

import { buildFusedCsv } from "./fixtures";

declare global {
  namespace Cypress {
    interface Chainable {
      /** Flush DB + reseed UVL via Django mgmt command, then return credentials. */
      resetBackend(opts?: { uvl?: string }): Chainable<TestState>;
      /** Persist a JWT login token into localStorage, skipping the UI form. */
      loginAs(role: "admin" | "tecnico"): Chainable<void>;
      /**
       * Drive the 4-step configurator wizard through the real UI until it
       * navigates to /validacion-modelo. Selections are UVL feature names
       * (data-cy="feature-<name>"), not Spanish labels.
       */
      completeWizard(opts?: WizardOptions): Chainable<void>;
      /**
       * Train a model directly via the API (fast precondition for specs that
       * need an existing trained model). Polls status to completion and yields
       * the model_id. Requires a prior cy.loginAs().
       */
      trainModelViaApi(opts?: TrainOptions): Chainable<string>;
      /**
       * Upload a CSV into a SensorFileCard identified by its visible label and
       * bind its timestamp/data columns. Operates on the card currently in view.
       */
      uploadSensorCard(
        label: string,
        content: string,
        fileName: string,
        timestampCol: string,
        dataCol: string,
      ): Chainable<void>;
    }
  }
}

export interface TestState {
  admin: { email: string; password: string; id: number };
  tecnico: { email: string; password: string; id: number };
  uvl_version_id: number;
  uvl_path: string;
}

export interface WizardOptions {
  treatment?: string;
  soil?: string;
  /** Sensor feature names to click, in render order (parents before children). */
  sensors?: string[];
  /** Telemetry index feature names to click. */
  telemetry?: string[];
  objective?: string;
}

export interface TrainOptions {
  features?: string[];
  geo?: Record<string, unknown>;
  csv?: string;
  isValidation?: boolean;
}

Cypress.Commands.add("resetBackend", (opts = {}) => {
  return cy.task<TestState>("resetBackend", opts);
});

Cypress.Commands.add("loginAs", (role: "admin" | "tecnico") => {
  const email = role === "admin" ? Cypress.env("adminEmail") : Cypress.env("tecnicoEmail");
  const password = role === "admin" ? Cypress.env("adminPassword") : Cypress.env("tecnicoPassword");
  // Visit the app first so the token is written to the app origin
  // (localhost:8080), independent of any prior cy.visit in the spec.
  cy.visit("/login");
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

// Default valid config under the v2 UVL: RiegoDeficitario + Luvisoles + TasaBuenos.
// Satisfies every constraint with the fewest sensors/telemetry:
//   RiegoDeficitario => (Hd35|Hd45|Hd55) & DPV,  Luvisoles => (NDVI|EVI),
//   TasaBuenos => DatoTB,  Dendrometro => (DatoMCD|DatoTB|DatoTS).
const DEFAULT_WIZARD: Required<WizardOptions> = {
  treatment: "RiegoDeficitario",
  soil: "Luvisoles",
  sensors: ["DatoTB", "HumedadSuelo", "Hd35", "DPV"],
  telemetry: ["NDVI"],
  objective: "TasaBuenos",
};

function clickFeature(name: string) {
  cy.get(`[data-cy="feature-${name}"]`, { timeout: 15000 }).click();
}

Cypress.Commands.add("completeWizard", (opts: WizardOptions = {}) => {
  const cfg = { ...DEFAULT_WIZARD, ...opts };

  cy.visit("/creacion-sensor-digital");

  // Step 1 — Parcela
  clickFeature(cfg.treatment);
  clickFeature(cfg.soil);
  cy.get("#parcela-provincia option").should("have.length.greaterThan", 1);
  cy.get("#parcela-provincia option")
    .eq(1)
    .then((opt) => cy.get("#parcela-provincia").select(String(opt.val())));
  cy.get("#parcela-municipio option", { timeout: 10000 }).should("have.length.greaterThan", 1);
  cy.get("#parcela-municipio option")
    .eq(1)
    .then((opt) => cy.get("#parcela-municipio").select(String(opt.val())));
  cy.get('[data-cy="wizard-parcel-next"]').should("not.be.disabled").click();

  // Step 2 — Sensores
  cfg.sensors.forEach(clickFeature);
  cy.get('[data-cy="wizard-sensors-next"]').should("not.be.disabled").click();

  // Step 3 — Telemetría
  cfg.telemetry.forEach(clickFeature);
  cy.get('[data-cy="wizard-telemetry-next"]').should("not.be.disabled").click();

  // Step 4 — Objetivo + validar
  clickFeature(cfg.objective);
  cy.get('[data-cy="wizard-generate"]').should("not.be.disabled").click();
  cy.location("pathname", { timeout: 15000 }).should("eq", "/validacion-modelo");
});

function pollTraining(modelId: string, token: string, attemptsLeft: number): Cypress.Chainable<string> {
  return cy
    .request({
      method: "GET",
      url: `${Cypress.env("backendUrl")}/api/v1/modelos/${modelId}/status`,
      headers: { Authorization: `Bearer ${token}` },
      failOnStatusCode: false,
    })
    .then((res) => {
      const status = (res.body as { status?: string }).status ?? "unknown";
      if (status === "completed") return cy.wrap(modelId);
      if (status === "error" || attemptsLeft <= 0) {
        throw new Error(`training did not complete (status=${status}): ${JSON.stringify(res.body)}`);
      }
      return cy.wait(2000).then(() => pollTraining(modelId, token, attemptsLeft - 1));
    });
}

Cypress.Commands.add("trainModelViaApi", (opts: TrainOptions = {}) => {
  const features = opts.features ?? ["RiegoDeficitario", "TasaBuenos"];
  const geo = opts.geo ?? { punto: { lat: 37.5, lng: -5.0 }, nombre: "Finca E2E" };
  const csv = opts.csv ?? buildFusedCsv(180);
  const isValidation = opts.isValidation ?? true;
  const backend = Cypress.env("backendUrl") as string;

  return cy
    .window()
    .then((win) => {
      const token = win.localStorage.getItem("access_token") as string;
      const fd = new win.FormData();
      fd.append("features", JSON.stringify(features));
      fd.append("geo", JSON.stringify(geo));
      fd.append("is_validation", String(isValidation));
      fd.append("csv_file", new win.Blob([csv], { type: "text/csv" }), "fused.csv");
      return win
        .fetch(`${backend}/api/v1/modelos/train`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: fd,
        })
        .then((r) => r.json().then((body) => ({ status: r.status, body, token })));
    })
    .then(({ status, body, token }) => {
      expect(status, "train accepted").to.eq(202);
      const modelId = (body as { model_id?: string }).model_id as string;
      expect(modelId, "model_id returned").to.be.a("string");
      return pollTraining(modelId, token, 40);
    });
});

Cypress.Commands.add(
  "uploadSensorCard",
  (label: string, content: string, fileName: string, timestampCol: string, dataCol: string) => {
    cy.contains('[data-cy="sensor-card"]', label).within(() => {
      cy.get('[data-cy="sensor-file-input"]').selectFile(
        { contents: Cypress.Buffer.from(content), fileName },
        { force: true },
      );
      cy.get('[data-cy="sensor-timestamp-col"]').select(timestampCol);
      cy.get('[data-cy="sensor-data-col"]').select(dataCol);
    });
  },
);

export {};
