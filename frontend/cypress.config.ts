import { defineConfig } from "cypress";
import { spawnSync } from "child_process";
import { existsSync } from "fs";
import { resolve } from "path";

/**
 * E2E config for agroTrain.
 *
 * `cy.task("resetBackend")` shells out to the Django management command
 * `reset_test_state` so each spec begins with a deterministic DB + active UVL.
 * Relying on the frontend alone cannot reset server state, so we drive Django
 * directly from Cypress.
 */

const backendDir = resolve(__dirname, "../backend");

/**
 * Resolve a Python interpreter that can run Django, portably across machines:
 * an explicit override wins, then the project venv (Unix + Windows layouts),
 * then `python3`/`python` from PATH. Avoids hard-coding `python`, which does not
 * exist by default on macOS (only `python3`).
 */
function resolvePython(): string {
  const candidates = [
    process.env.CYPRESS_PYTHON,
    resolve(backendDir, ".venv/bin/python"),
    resolve(backendDir, ".venv/Scripts/python.exe"),
    resolve(backendDir, "venv/bin/python"),
    resolve(backendDir, "venv/Scripts/python.exe"),
  ].filter(Boolean) as string[];

  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  // Fall back to a PATH lookup; pick the first that actually runs.
  for (const name of ["python3", "python"]) {
    if (spawnSync(name, ["--version"]).status === 0) return name;
  }
  throw new Error(
    "No Python interpreter found. Create a venv at backend/.venv or set CYPRESS_PYTHON.",
  );
}

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
      const python = resolvePython();
      on("task", {
        resetBackend(opts: { uvl?: string } = {}) {
          const args = ["manage.py", "reset_test_state", "--json"];
          if (opts.uvl) args.push("--uvl", opts.uvl);
          const result = spawnSync(python, args, { cwd: backendDir });
          if (result.status !== 0) {
            return Promise.reject(
              new Error(
                `reset_test_state failed (python: ${python}): ${result.stderr?.toString() ?? "unknown error"}`,
              ),
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
