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
 * The command MUST run against the same DB the server under test reads. The
 * server runs inside the `backend` Docker container (Postgres), so we exec the
 * command there via `docker compose exec`. Running a host Python interpreter
 * would instead hit the dev SQLite file and seed users the container never
 * sees, yielding 401 on login. Override the runner with `CYPRESS_RESET_CMD`
 * (space-separated) if you run the backend outside Docker.
 */

const repoRoot = resolve(__dirname, "..");

/**
 * Argv that runs `reset_test_state` inside the running backend container.
 * `-T` disables TTY allocation so spawnSync can capture stdout cleanly.
 */
function resetRunner(): string[] {
  const override = process.env.CYPRESS_RESET_CMD;
  if (override) return override.split(" ").filter(Boolean);
  return ["docker", "compose", "exec", "-T", "backend", "python"];
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
