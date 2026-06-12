/**
 * Fills the configurator wizard with concrete field values.
 *
 * Feature selections are driven by the active UVL fixture
 * (`v2_olivos_tratamientos.uvl`): treatment `RiegoControl` ("Riego control"),
 * soil `Calcisoles` ("Suelos calizos (calcisoles)"), and the sensor subtree
 * `HumedadSuelo` → `Hd35` plus `TemperaturaAire` (mandatory for RiegoControl).
 * No feature names are hardcoded in app code — they come from the UVL tree, so
 * this test exercises the UVL → wizard rendering + selection path end to end.
 */
describe("Wizard fill — parcel + UVL feature selection", () => {
  beforeEach(() => {
    cy.resetBackend();
    cy.visit("/");
    cy.loginAs("tecnico");
    cy.visit("/creacion-sensor-digital");
  });

  it("fills parcel data and advances to the sensors step", () => {
    // Parcel name
    cy.get("#parcela-nombre", { timeout: 10000 })
      .type("Finca E2E Los Olivos")
      .should("have.value", "Finca E2E Los Olivos");

    // Province: pick the first real option (index 0 is the placeholder)
    cy.get("#parcela-provincia option").should("have.length.greaterThan", 1);
    cy.get("#parcela-provincia option")
      .eq(1)
      .then((opt) => cy.get("#parcela-provincia").select(opt.val() as string));

    // Municipality: loads after province selection
    cy.get("#parcela-municipio option", { timeout: 10000 }).should(
      "have.length.greaterThan",
      1,
    );
    cy.get("#parcela-municipio option")
      .eq(1)
      .then((opt) => cy.get("#parcela-municipio").select(opt.val() as string));

    // UVL ALTERNATIVE groups: treatment + soil (rendered as buttons by FeatureNode)
    cy.contains("button", /^Riego control$/).click();
    cy.contains("button", "Suelos calizos").click();

    // Parcel step is ready once treatment + soil + province + municipio are set
    // (parcelStepReady in DigitalSensorCreation.tsx — no map point required here;
    // the parcel point/geometry now lives in the telemetry step) — advance
    cy.contains("button", "Listo, continuar a sensores físicos")
      .should("not.be.disabled")
      .click();

    // Step 2 (StepSensores) rendered from the UVL ParametrosEntrada subtree
    cy.contains("Parámetros de entrada", { timeout: 10000 }).should("exist");
    cy.contains("Dendrómetro").should("exist"); // mandatory chip

    // Select UVL sensor features: HumedadSuelo → 35 cm, plus TemperaturaAire
    cy.contains("button", "Humedad del suelo").click();
    cy.contains("button", /^35 cm$/).click();
    cy.contains("button", "Temperatura del aire").click();

    // Selected feature buttons show the active check icon
    cy.contains("button", /^35 cm$/).find("svg").should("exist");
    cy.contains("button", "Temperatura del aire").find("svg").should("exist");
  });
});
