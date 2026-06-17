import { defineConfig } from "cypress";
import { spawnSync } from "child_process";
import { resolve } from "path";

/**
 * E2E config for agroTrain.
 *
 * `cy.task("resetBackend")` runs the Django management command
 * `reset_test_state` so each spec begins with a deterministic DB + active UVL.
 * Relying on the frontend alone cannot reset server state, so we drive Django
 * directly from Cypress.
 *
 * reset_test_state FLUSHES the DB before every spec, so it must NOT run against
 * the developer's dev stack (that wipes their users → login breaks). It targets
 * the isolated E2E stack defined in `docker-compose.e2e.yml`: a throwaway
 * `backend-e2e` container on :8001 backed by its own `agrotrain_e2e` Postgres
 * volume, served by `frontend-e2e` on :8081. The dev `backend` (:8000, DB
 * `agrotrain`) is never touched. Override the runner with `CYPRESS_RESET_CMD`
 * (space-separated) if you run the backend elsewhere.
 *
 * Bring the E2E stack up first:
 *   docker compose -f docker-compose.yml -f docker-compose.e2e.yml up \
 *     db-e2e backend-e2e frontend-e2e
 */

const repoRoot = resolve(__dirname, "..");

/**
 * Argv that runs `reset_test_state` inside the isolated E2E backend container.
 * `-T` disables TTY allocation so spawnSync can capture stdout cleanly.
 */
function resetRunner(): string[] {
  const override = process.env.CYPRESS_RESET_CMD;
  if (override) return override.split(" ").filter(Boolean);
  return [
    "docker",
    "compose",
    "-f",
    "docker-compose.yml",
    "-f",
    "docker-compose.e2e.yml",
    "exec",
    "-T",
    "backend-e2e",
    "python",
  ];
}

export default defineConfig({
  e2e: {
    baseUrl: "http://localhost:8081",
    env: {
      backendUrl: "http://localhost:8001",
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
          const [cmd, ...base] = resetRunner();
          const args = [...base, "manage.py", "reset_test_state", "--json"];
          if (opts.uvl) args.push("--uvl", opts.uvl);
          const result = spawnSync(cmd, args, { cwd: repoRoot });
          if (result.status !== 0) {
            return Promise.reject(
              new Error(
                `reset_test_state failed (${cmd} ${args.join(" ")}): ${result.stderr?.toString() ?? "unknown error"}`,
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
