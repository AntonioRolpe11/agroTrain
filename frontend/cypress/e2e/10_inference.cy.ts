/**
 * Inference / value generation (GenerarValorModelo).
 *
 * Covers `POST /api/v1/modelos/<id>/predict` and
 * `GET  /api/v1/modelos/<id>/predictions`.
 *
 * Guards exercised (modelos/views.py + prediction_service.py):
 *   - predict requires the model to have `geo.punto` saved (400 otherwise),
 *   - predict requires a `csv_file` (400 otherwise),
 *   - one-step-ahead predict on a fused CSV → 201 with a `predictions` dict.
 *
 * Trains a `TasaBuenos` / `RiegoControl` model with a saved point so predict's
 * location guard passes; the model only needs `date;TasaBuenos`, so a CSV of
 * ≥ window_size consecutive recent rows is a valid prediction input.
 */
const BACKEND = Cypress.env("backendUrl") as string;

function buildFusedCsv(rows: number, startISO = "2022-01-01"): string {
  const lines = ["date;TasaBuenos"];
  const start = new Date(`${startISO}T00:00:00Z`);
  for (let i = 0; i < rows; i++) {
    const d = new Date(start.getTime() + i * 86400000);
    const iso = d.toISOString().slice(0, 10);
    const v = 0.55 + 0.2 * Math.sin(i / 9) + 0.03 * Math.cos(i / 3);
    lines.push(`${iso};${v.toFixed(4)}`);
  }
  return lines.join("\n");
}

describe("Inferencia: generar valor", () => {
  let authToken = "";

  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("tecnico");
    cy.window().then((win) => {
      authToken = win.localStorage.getItem("access_token") as string;
    });
  });

  function trainModelWithPoint(): Cypress.Chainable<string> {
    const features = ["RiegoControl", "Calcisoles", "TasaBuenos"];
    const csv = buildFusedCsv(180);
    return cy
      .window()
      .then((win) => {
        const fd = new win.FormData();
        fd.append("features", JSON.stringify(features));
        fd.append("geo", JSON.stringify({ punto: { lat: 37.5, lng: -5.0 } }));
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
          .then((r) => r.json());
      })
      .then((body) => cy.wrap((body as { model_id: string }).model_id));
  }

  function pollUntilCompleted(
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
        const status = (res.body as { status?: string }).status ?? "unknown";
        if (status === "completed" || status === "error" || attemptsLeft <= 0) {
          expect(status, "training completed").to.eq("completed");
          return cy.wrap(modelId);
        }
        return cy
          .wait(2000)
          .then(() => pollUntilCompleted(modelId, attemptsLeft - 1));
      });
  }

  it("predice un valor one-step-ahead y lo registra en el histórico", () => {
    trainModelWithPoint()
      .then((id) => pollUntilCompleted(id, 30))
      .then((modelId) => {
        // 1. Histórico vacío recién entrenado
        cy.request({
          method: "GET",
          url: `${BACKEND}/api/v1/modelos/${modelId}/predictions`,
          headers: { Authorization: `Bearer ${authToken}` },
        }).then((res) => {
          expect(res.status).to.eq(200);
          expect(res.body.predictions).to.be.an("array").and.to.have.length(0);
        });

        // 2. predict sin CSV → 400
        cy.request({
          method: "POST",
          url: `${BACKEND}/api/v1/modelos/${modelId}/predict`,
          headers: { Authorization: `Bearer ${authToken}` },
          failOnStatusCode: false,
        }).then((res) => {
          expect(res.status).to.eq(400);
          expect(JSON.stringify(res.body)).to.contain("CSV");
        });

        // 3. predict con CSV válido → 201 + predictions dict
        const csv = buildFusedCsv(60, "2023-01-01");
        cy.window().then((win) => {
          const fd = new win.FormData();
          fd.append(
            "csv_file",
            new win.Blob([csv], { type: "text/csv" }),
            "fused.csv",
          );
          return win
            .fetch(`${BACKEND}/api/v1/modelos/${modelId}/predict`, {
              method: "POST",
              headers: { Authorization: `Bearer ${authToken}` },
              body: fd,
            })
            .then((r) => r.json().then((body) => ({ status: r.status, body })))
            .then(({ status, body }) => {
              expect(status, "predict 201").to.eq(201);
              expect(body.predictions, "predictions dict").to.have.property(
                "TasaBuenos",
              );
              expect(body).to.have.property("predicted_for_date");
              expect(body.input_row_count).to.eq(60);
            });
        });

        // 4. El histórico ahora tiene una predicción
        cy.request({
          method: "GET",
          url: `${BACKEND}/api/v1/modelos/${modelId}/predictions`,
          headers: { Authorization: `Bearer ${authToken}` },
        })
          .its("body.predictions")
          .should("have.length", 1);
      });
  });
});
