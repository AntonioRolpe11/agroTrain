/**
 * Guardar / cargar / borrar configuraciones del wizard + importar JSON.
 * Todo por la UI del configurador (DigitalSensorCreation).
 */
describe("Configuraciones guardadas", () => {
  beforeEach(() => {
    cy.resetBackend();
    cy.loginAs("tecnico");
    cy.on("window:confirm", () => true);
  });

  function fillParcel() {
    cy.get('[data-cy="feature-RiegoDeficitario"]', { timeout: 15000 }).click();
    cy.get('[data-cy="feature-Luvisoles"]').click();
    cy.get("#parcela-provincia option").should("have.length.greaterThan", 1);
    cy.get("#parcela-provincia option").eq(1).then((o) => cy.get("#parcela-provincia").select(String(o.val())));
    cy.get("#parcela-municipio option", { timeout: 10000 }).should("have.length.greaterThan", 1);
    cy.get("#parcela-municipio option").eq(1).then((o) => cy.get("#parcela-municipio").select(String(o.val())));
  }

  it("guarda una configuración, la lista, la carga y la borra", () => {
    cy.visit("/creacion-sensor-digital");
    fillParcel();

    // Guardar
    cy.get('[data-cy="config-save-toggle"]').click();
    cy.get('[data-cy="config-save-name"]').type("Config E2E");
    cy.get('[data-cy="config-save-submit"]').click();

    // Recargar y comprobar que aparece en la lista
    cy.visit("/creacion-sensor-digital");
    cy.get('[data-cy="config-list-toggle"]').click();
    cy.get('[data-cy="config-item"]').should("have.length", 1).and("contain", "Config E2E");

    // Cargar → el tratamiento queda seleccionado (icono de check activo)
    cy.get('[data-cy="config-load"]').click();
    cy.get('[data-cy="feature-RiegoDeficitario"]').find("svg").should("exist");
    cy.get("#parcela-provincia").should("not.have.value", "");

    // Borrar (el panel sigue abierto tras borrar → debe quedar vacío)
    cy.get('[data-cy="config-list-toggle"]').click();
    cy.get('[data-cy="config-delete"]').click();
    cy.contains("No tienes configuraciones guardadas").should("be.visible");
  });

  it("importa una configuración desde un archivo JSON", () => {
    cy.visit("/creacion-sensor-digital");
    // Espera a que el modelo cargue (el import se ignora si aún no hay modelo)
    cy.get('[data-cy="feature-RiegoDeficitario"]', { timeout: 15000 }).should("exist");
    const config = {
      version: 1,
      features: ["RiegoDeficitario", "Luvisoles", "DatoTB", "TasaBuenos"],
      geo: { nombre: "Importada E2E", cloudThreshold: 20 },
    };
    cy.get('[data-cy="config-import-input"]').selectFile(
      { contents: Cypress.Buffer.from(JSON.stringify(config)), fileName: "config.json" },
      { force: true },
    );
    // La feature importada queda activa en el wizard
    cy.get('[data-cy="feature-RiegoDeficitario"]', { timeout: 10000 }).find("svg").should("exist");
    cy.get("#parcela-nombre").should("have.value", "Importada E2E");
  });
});
