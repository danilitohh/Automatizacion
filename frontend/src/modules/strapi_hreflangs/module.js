"use strict";

import { hreflangsApi } from "./api.js";

const LOCALE_NAMES = {
  "es-mx": "México", "es-co": "Colombia", "es-pe": "Perú", "es-ec": "Ecuador",
  "es-us": "USA", "es-ar": "Argentina", "es-do": "República Dominicana", "es-gt": "Guatemala",
  "es-cl": "Chile", "es-sv": "El Salvador", "es-bo": "Bolivia", "es-pa": "Panamá", "es-py": "Paraguay",
};

function escapeHtml(value) {
  // Los datos obtenidos desde Strapi se escapan antes de insertarlos en el DOM.
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function setBusy(busy) {
  // Evita iniciar trabajos simultáneos mientras hay uno en curso.
  document.querySelector("#hreflang-dry-run").disabled = busy;
  document.querySelector("#hreflang-apply").disabled = busy || !state.configured || !state.previewJobId;
}

const state = { configured: false, host: "", currentJob: null, pollTimer: null, results: [], previewJobId: "", previewParams: null };

function renderResults(results) {
  // Resume cada producto procesado con estado, total de enlaces y errores relevantes.
  const counts = results.reduce((acc, item) => ({ ...acc, [item.action]: (acc[item.action] || 0) + 1 }), {});
  const labels = { updated: "Actualizados", "would-update": "Se agregarían", unchanged: "Sin cambios", error: "Errores" };
  document.querySelector("#hreflang-summary").innerHTML = Object.entries(labels)
    .map(([key, label]) => `<div class="pdp-summary-card"><strong>${counts[key] || 0}</strong><span>${label}</span></div>`)
    .join("");
  const list = document.querySelector("#hreflang-results");
  list.innerHTML = results.length ? results.map((item) => `
    <article class="hreflang-result ${item.action === "error" ? "error" : ""}">
      <strong>${escapeHtml(item.product_name || item.slug)} · ${escapeHtml(item.action)}</strong>
      <small>${escapeHtml(item.locale)} / ${escapeHtml(item.slug)} · ${item.added?.length || 0} enlaces agregados</small>
      ${item.error ? `<small>${escapeHtml(item.error)}</small>` : ""}
    </article>`).join("") : "Sin productos para mostrar.";
}

async function pollJob(jobId) {
  // Sigue el trabajo y agrega los mensajes nuevos al terminal de actividad.
  let offset = 0;
  const terminal = document.querySelector("#hreflang-progress");
  while (state.currentJob === jobId) {
    const job = await hreflangsApi.status(jobId, offset);
    const messages = job.progress || [];
    if (messages.length) {
      terminal.textContent = `${terminal.textContent}\n${messages.join("\n")}`.trim().split("\n").slice(-300).join("\n");
      offset = job.progress_offset;
    }
    document.querySelector("#hreflang-status").textContent = job.message || `${job.completed || 0} productos · ${job.status}`;
    if (["SUCCESS", "WARNING", "FAILED"].includes(job.status)) {
      if (job.results) {
        state.results = job.results;
        renderResults(job.results);
      }
      if (job.download_url) {
        const report = document.querySelector("#hreflang-report");
        report.href = hreflangsApi.reportUrl(jobId);
        report.hidden = false;
      }
      document.querySelector("#hreflang-run-title").textContent = job.status === "FAILED" ? "Ejecución fallida" : "Ejecución terminada";
      setBusy(false);
      if (job.mode === "dry-run" && job.status !== "FAILED" && state.results.some((item) => item.action === "would-update")) {
        state.previewJobId = jobId;
        document.querySelector("#hreflang-apply").disabled = false;
      } else if (job.mode === "apply") {
        state.previewJobId = "";
        state.previewParams = null;
        document.querySelector("#hreflang-apply").disabled = true;
      }
      return job;
    }
    await new Promise((resolve) => { state.pollTimer = window.setTimeout(resolve, 1200); });
  }
}

async function startRun(apply) {
  // La escritura exige que el operador confirme textualmente el host que verá el backend.
  const locale = document.querySelector("#hreflang-locale").value;
  const scope = document.querySelector("#hreflang-scope").value;
  const maxProducts = scope === "limit" ? Number(document.querySelector("#hreflang-limit").value) : null;
  if (apply && (!state.previewJobId || JSON.stringify(state.previewParams) !== JSON.stringify({ locale, maxProducts }))) {
    document.querySelector("#hreflang-status").textContent = "Los parámetros cambiaron; vuelve a ejecutar la simulación antes de aplicar.";
    document.querySelector("#hreflang-apply").disabled = true;
    return;
  }
  let confirmation = "";
  if (apply) {
    confirmation = window.prompt(`Vas a modificar Strapi en ${state.host}. Escribe exactamente: APLICAR ${state.host}`) || "";
    if (!confirmation) return;
  }
  clearTimeout(state.pollTimer);
  document.querySelector("#hreflang-report").hidden = true;
  document.querySelector("#hreflang-progress").textContent = apply ? "Iniciando aplicación…" : "Iniciando simulación de solo lectura…";
  document.querySelector("#hreflang-results").textContent = "Procesando productos…";
  document.querySelector("#hreflang-run-title").textContent = apply ? "Aplicando cambios" : "Simulando cambios";
  document.querySelector("#hreflang-mode").textContent = apply ? "Escritura confirmada" : "Solo lectura";
  document.querySelector("#hreflang-status").textContent = "Conectando con Strapi y revisando equivalencias.";
  state.results = [];
  if (!apply) {
    state.previewJobId = "";
    state.previewParams = null;
  }
  setBusy(true);
  try {
    const job = await hreflangsApi.run({ locale, max_products: maxProducts, apply, confirmation, expected_host: state.host, preview_job_id: state.previewJobId });
    state.currentJob = job.job_id;
    if (!apply) state.previewParams = { locale, maxProducts };
    await pollJob(job.job_id);
  } catch (error) {
    document.querySelector("#hreflang-status").textContent = error.message;
    document.querySelector("#hreflang-run-title").textContent = "No se pudo iniciar";
    setBusy(false);
  }
}

export function initializeHreflangsModule() {
  // Conecta controles propios del panel y consulta la configuración no sensible.
  const dryRun = document.querySelector("#hreflang-dry-run");
  const apply = document.querySelector("#hreflang-apply");
  const invalidatePreview = () => {
    // Un cambio de locale o alcance obliga a volver a revisar ese plan antes de escribir.
    state.previewJobId = "";
    state.previewParams = null;
    apply.disabled = true;
  };
  document.querySelector("#hreflang-scope").addEventListener("change", (event) => {
    document.querySelector("#hreflang-limit").hidden = event.target.value !== "limit";
    invalidatePreview();
  });
  document.querySelector("#hreflang-locale").addEventListener("change", invalidatePreview);
  document.querySelector("#hreflang-limit").addEventListener("input", invalidatePreview);
  dryRun.addEventListener("click", () => startRun(false));
  apply.addEventListener("click", () => startRun(true));
  hreflangsApi.config().then((config) => {
    state.configured = config.configured;
    state.host = config.host || "";
    document.querySelector("#hreflang-target-host").value = config.host || "No configurado";
    document.querySelector("#hreflang-config-status").textContent = config.configured ? "CONFIGURADO" : "SIN CONFIGURAR";
    document.querySelector("#hreflang-config-status").className = `status-badge ${config.configured ? "success" : "error"}`;
    const select = document.querySelector("#hreflang-locale");
    select.innerHTML = (config.locales || []).map((locale) => `<option value="${escapeHtml(locale)}">${escapeHtml(LOCALE_NAMES[locale] || locale)} (${escapeHtml(locale)})</option>`).join("");
    select.disabled = !config.configured;
    dryRun.disabled = !config.configured;
    apply.disabled = !config.configured;
    document.querySelector("#hreflang-status").textContent = config.configured
      ? `Listo. El token está configurado en backend; destino: ${config.host}.`
      : "Configura STRAPI_URL y STRAPI_TOKEN en el backend para habilitar este módulo.";
  }).catch((error) => {
    document.querySelector("#hreflang-config-status").textContent = "ERROR";
    document.querySelector("#hreflang-status").textContent = error.message;
  });
}
