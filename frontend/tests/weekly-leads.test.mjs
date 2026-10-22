import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";

const moduleScript = fs.readFileSync(new URL("../src/modules/weekly_auto/weekly_leads/module.js", import.meta.url), "utf8");
const sharedScript = fs.readFileSync(new URL("../src/modules/weekly_auto/lead_submission/module.js", import.meta.url), "utf8");
const apiScript = fs.readFileSync(new URL("../src/services/api.js", import.meta.url), "utf8");

test("Los selectores antiguos de Chrome ahora representan incógnito", () => {
  // Conservar el valor chrome permite cargar configuraciones previas sin usar su perfil.
  for (const path of ["../index.html", "../src/modules/bot_nuevos_productos/module.js",
    "../src/modules/bot_leads_deploy/module.js", "../src/renderer/bot-module.js",
    "../src/renderer/leads-deploy-module.js"]) {
    const source = fs.readFileSync(new URL(path, import.meta.url), "utf8");
    assert.doesNotMatch(source, /Perfil QA/);
    assert.match(source, /value="chrome">Google Chrome - Incógnito/);
  }
});

test("Todos los flujos de formularios ofrecen incógnito y no el perfil QA", () => {
  // Montar el controlador con un DOM mínimo comprueba el HTML que se entrega.
  for (const automationModule of ["weekly_forms", "weekly_leads", "form_validation"]) {
    let markup = "";
    const view = { insertAdjacentHTML: (_position, html) => { markup = html; } };
    const document = { querySelector: selector => selector === "#test-view" ? view
      : selector.endsWith("-panel") ? null : { addEventListener() {} } };
    const context = vm.createContext({ document });
    vm.runInContext(sharedScript.replace("export function", "function"), context);
    context.initializeLeadSubmissionModule({}, { automationModule, viewId: "test-view" });
    assert.match(markup, /value="chrome_incognito" selected/);
    assert.match(markup, /sin perfiles personales ni corporativos/);
    assert.doesNotMatch(markup, /Perfil QA/);
  }
});

test("Weekly Leads tiene identidad y controles independientes", () => {
  assert.match(moduleScript, /initializeWeeklyLeadsModule/);
  assert.match(moduleScript, /weekly_leads/);
  assert.match(moduleScript, /weekly-leads/);
  assert.match(sharedScript, /5 filas y descansa 60 segundos/);
});

test("Weekly Leads analiza su matriz y usa el lote existente de envíos", () => {
  assert.match(apiScript, /\/api\/weekly-auto\/leads\/spreadsheet-preview/);
  assert.match(apiScript, /runWeeklyLeadsBatch/);
  assert.match(apiScript, /automation_module: "weekly_leads"/);
  assert.match(apiScript, /\/api\/weekly-auto\/leads\/run/);
});

test("Form Validation acepta URLs manuales y conserva la búsqueda dual configurable", () => {
  assert.match(sharedScript, /allowManualUrls/);
  assert.match(sharedScript, /URLs de landings QA/);
  assert.match(sharedScript, /parallel_crm_search: true/);
  assert.match(apiScript, /\/api\/form-validation\/urls\/preview/);
  assert.match(apiScript, /\/api\/form-validation\/urls\/run/);
  assert.match(sharedScript, /Solo llenar, no enviar/);
  assert.match(sharedScript, /fill_only: Boolean\(element\("fill-only"\)\?\.checked\)/);
});
