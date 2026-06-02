import { defineConfig } from "cypress";
import { spawnSync } from "child_process";
import { resolve } from "path";

/**
 * E2E config for agroTrain.
 *
 * `cy.task("resetBackend")` shells out to the Django management command
 * `reset_test_state` so each spec begins with a deterministic DB + active UVL.
 * Pattern recommended by the team's E2E expert: relying on the frontend alone
 * cannot reset server state, so we drive Django directly from Cypress.
 */
export default defineConfig({
  e2e: {
    baseUrl: "http://localhost:8080",
    env: {
      backendUrl: "http://localhost:8000",
      adminEmail: "admin@test.local",
      adminPassword: "admin1234",
      tecnicoEmail: "tecnico@test.local",
      tecnicoPassword: "tecnico1234",
    },
    specPattern: "cypress/e2e/**/*.cy.ts",
    supportFile: "cypress/support/e2e.ts",
    fixturesFolder: "cypress/fixtures",
    video: false,
    screenshotOnRunFailure: false,
    setupNodeEvents(on) {
      on("task", {
        resetBackend(opts: { uvl?: string } = {}) {
          const backendDir = resolve(__dirname, "../backend");
          const args = ["manage.py", "reset_test_state", "--json"];
          if (opts.uvl) args.push("--uvl", opts.uvl);
          const result = spawnSync("python", args, { cwd: backendDir });
          if (result.status !== 0) {
            return Promise.reject(
              new Error(`reset_test_state failed: ${result.stderr?.toString() ?? "unknown error"}`),
            );
          }
          try {
            // Last line of stdout is the JSON payload
            const lines = result.stdout.toString().trim().split("\n");
            return JSON.parse(lines[lines.length - 1]);
          } catch (exc) {
            return Promise.reject(new Error(`reset_test_state output not JSON: ${exc}`));
          }
        },
      });
    },
  },
});
