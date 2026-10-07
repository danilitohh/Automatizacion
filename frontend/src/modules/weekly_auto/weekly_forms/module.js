"use strict";

import { initializeLeadSubmissionModule } from "../lead_submission/module.js";

const MANUAL_COUNTRIES = [
  ["Mexico", "México"], ["Colombia", "Colombia"], ["Dominicana", "República Dominicana"],
  ["USA", "Estados Unidos"], ["Argentina", "Argentina"], ["Bolivia", "Bolivia"],
  ["Ecuador", "Ecuador"], ["Peru", "Perú"], ["Chile", "Chile"], ["Panama", "Panamá"],
  ["Paraguay", "Paraguay"], ["Guatemala", "Guatemala"], ["El Salvador", "El Salvador"],
  ["India", "India"], ["Indonesia", "Indonesia"], ["Filipinas", "Filipinas"],
  ["Singapur", "Singapur"], ["Vietnam", "Vietnam"], ["Global", "Global"],
].map(([value, label]) => ({ value, label }));

// Conserva la entrada pública histórica de Weekly Forms y su contrato visual.
export function initializeWeeklyFormsModule(dependencies) {
  initializeLeadSubmissionModule(dependencies, {
    key: "weekly-forms",
    title: "Weekly Forms",
    fileLabel: "Excel de Weekly Forms (.xlsx)",
    description: "Lee Country, Nivel, Activo de Test, Location y Lead; también acepta URLs pegadas.",
    readyMessage: "Selecciona la matriz QA.",
    runLabel: "Ejecutar Weekly Forms",
    automationModule: "weekly_forms",
    viewId: "view-weekly-forms",
    allowManualUrls: true,
    manualCountryOptions: MANUAL_COUNTRIES,
    manualCountryRequired: true,
    previewManualUrls: dependencies.previewWeeklyFormsUrls,
    runManualUrls: dependencies.runWeeklyFormsUrls,
  });
}
