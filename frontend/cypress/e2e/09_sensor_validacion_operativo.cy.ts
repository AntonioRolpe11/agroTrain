/**
 * Sensor digital "de validación" vs "operativo" (commit b516d87).
 *
 * `Results.tsx` lets the user pick between a validation sensor (80/20 split,
 * produces metrics) and an operative sensor (trains on 100% of the data, no
 * validation metrics). The flag travels to `POST /api/v1/modelos/train` as the
 * multipart field `is_validation` ("false" → operativo; default → validación,
 * train_model view modelos/views.py:160). This spec drives that contract at the
 * API level — the full UI path (upload → fuse → train) is exercised elsewhere.
 *
 * Target `TasaBuenos` under `RiegoControl` (UVL fixture) needs only a
 * `date;TasaBuenos` CSV to complete, so the run stays fast and deterministic.
 */
const BACKEND = Cypress.env("backendUrl") as string;

function buildFusedCsv(rows: number): string {
  const lines = ["date;TasaBuenos"];
  const start = new Date("2022-01-01T00:00:00Z");
  for (let i = 0; i < rows; i++) {
    const d = new Date(start.getTime() + i * 86400000);
    const iso = d.toISOString().slice(0, 10);
    const v = 0.55 + 0.2 * Math.sin(i / 9) + 0.03 * Math.cos(i / 3);
    lines.push(`${iso};${v.toFixed(4)}`);
  }
  return lines.join("\n");
}

describe("Sensor digital: validación vs operativo", () => {
  let authToken = "";

  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("tecnico");
    cy.window().then((win) => {
      authToken = win.localStorage.getItem("access_token") as string;
    });
  });

  function train(isValidation: boolean): Cypress.Chainable<string> {
    const features = ["RiegoControl", "Calcisoles", "TasaBuenos"];
    const csv = buildFusedCsv(180);
    return cy
      .window()
      .then((win) => {
        const fd = new win.FormData();
        fd.append("features", JSON.stringify(features));
        fd.append("geo", JSON.stringify({ punto: { lat: 37.5, lng: -5.0 } }));
        if (!isValidation) fd.append("is_validation", "false");
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
        return cy.wrap(modelId as string);
      });
  }

  function pollStatus(
    modelId: string,
    attemptsLeft: number,
  ): Cypress.Chainable<Record<string, unknown>> {
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
          return cy.wrap(res.body as Record<string, unknown>);
        }
        return cy.wait(2000).then(() => pollStatus(modelId, attemptsLeft - 1));
      });
  }

  it("validación → produce métricas y partición de validación", () => {
    train(true)
      .then((id) => pollStatus(id, 30))
      .then((body) => {
        expect(body.status, "completed").to.eq("completed");
        expect(body.is_validation, "is_validation flag").to.eq(true);
        expect(body.n_val as number, "n_val > 0").to.be.greaterThan(0);
        expect(
          Object.keys(body.metrics as Record<string, unknown>),
          "metrics no vacío",
        ).to.have.length.greaterThan(0);
      });
  });

  it("operativo → sin métricas ni partición de validación", () => {
    train(false)
      .then((id) => pollStatus(id, 30))
      .then((body) => {
        expect(body.status, "completed").to.eq("completed");
        expect(body.is_validation, "is_validation flag").to.eq(false);
        expect(body.n_val as number, "n_val == 0").to.eq(0);
        expect(
          Object.keys(body.metrics as Record<string, unknown>),
          "metrics vacío",
        ).to.have.length(0);
      });
  });
});
