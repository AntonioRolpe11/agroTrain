/**
 * CSV ingestion through the training endpoint.
 *
 * Posts a synthetic fused CSV to `POST /api/v1/modelos/train` and polls
 * `GET /api/v1/modelos/<id>/status` until the async pipeline reaches a
 * terminal state. Uses the `TasaBuenos` objective under the `RiegoControl`
 * treatment: that maps (via the UVL fixture) to the `control_tasabuenos_svr_v1`
 * hyperprofile whose `feature_variant` is `target_only` and `required_inputs`
 * is empty, so the CSV only needs `date` + `TasaBuenos` columns and the
 * pipeline can complete without telemetry/sensor inputs.
 */
const BACKEND = Cypress.env("backendUrl") as string;

function buildFusedCsv(rows: number): string {
  const lines = ["date;TasaBuenos"];
  const start = new Date("2022-01-01T00:00:00Z");
  for (let i = 0; i < rows; i++) {
    const d = new Date(start.getTime() + i * 86400000);
    const iso = d.toISOString().slice(0, 10);
    // Smooth seasonal signal + mild deterministic noise (stable, no RNG)
    const v = 0.55 + 0.2 * Math.sin(i / 9) + 0.03 * Math.cos(i / 3);
    lines.push(`${iso};${v.toFixed(4)}`);
  }
  return lines.join("\n");
}

describe("CSV ingestion via training endpoint", () => {
  let authToken = "";

  beforeEach(() => {
    cy.resetBackend();
    cy.visit("/");
    cy.loginAs("tecnico");
    cy.window().then((win) => {
      authToken = win.localStorage.getItem("access_token") as string;
    });
  });

  function pollStatus(
    modelId: string,
    attemptsLeft: number,
  ): Cypress.Chainable<string> {
    return cy
      .request({
        method: "GET",
        url: `${BACKEND}/api/v1/modelos/${modelId}/status`,
        headers: { Authorization: `Bearer ${authToken}` },
        failOnStatusCode: false,
      })
      .then((res) => {
        expect(res.status, "status endpoint reachable").to.not.eq(404);
        const status = (res.body as { status?: string }).status ?? "unknown";
        if (status === "completed" || status === "error" || attemptsLeft <= 0) {
          // Ingestion proof: the failure (if any) must not be a CSV read /
          // missing-column error — the pipeline got past CSV parsing.
          const detail = String((res.body as { detail?: string }).detail ?? "");
          expect(detail).to.not.contain("Error leyendo CSV");
          expect(detail).to.not.contain("Columnas ausentes en CSV");
          return cy.wrap(status);
        }
        return cy.wait(2000).then(() => pollStatus(modelId, attemptsLeft - 1));
      });
  }

  it("accepts a fused CSV and runs the training pipeline to completion", () => {
    const features = ["RiegoControl", "Calcisoles", "TasaBuenos"];
    const csv = buildFusedCsv(180);

    cy.window()
      .then((win) => {
        const fd = new win.FormData();
        fd.append("features", JSON.stringify(features));
        fd.append("geo", JSON.stringify({ lat: 37.5, lng: -5.0 }));
        fd.append(
          "csv_file",
          new win.Blob([csv], { type: "text/csv" }),
          "fused.csv",
        );
        return win
          .fetch(`${BACKEND}/api/v1/modelos/train`, {
            method: "POST",
            headers: { Authorization: `Bearer ${authToken}` },
            body: fd,
          })
          .then((r) => r.json().then((body) => ({ status: r.status, body })));
      })
      .then(({ status, body }) => {
        expect(status, "train accepted (202)").to.eq(202);
        const modelId = (body as { model_id?: string }).model_id;
        expect(modelId, "model_id returned").to.be.a("string");
        return pollStatus(modelId as string, 30);
      })
      .then((finalStatus) => {
        expect(finalStatus, "pipeline reached completed (not error)").to.eq(
          "completed",
        );
      });
  });

  it("rejects a training request without a CSV file (400)", () => {
    cy.request({
      method: "POST",
      url: `${BACKEND}/api/v1/modelos/train`,
      headers: { Authorization: `Bearer ${authToken}` },
      form: true,
      body: { features: JSON.stringify(["RiegoControl", "TasaBuenos"]) },
      failOnStatusCode: false,
    }).then((res) => {
      expect(res.status).to.eq(400);
      expect(JSON.stringify(res.body)).to.contain("CSV");
    });
  });
});
