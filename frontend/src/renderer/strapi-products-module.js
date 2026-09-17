"use strict";

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function renderResults(job) {
  const results = job.results || [];
  const summary = { ...(job.summary || {}) };
  if (results.some((item) => item.verification)) {
    summary.productos_verificados = results.filter((item) => item.verification?.ok === true).length;
    summary.fallos_verificacion = results.filter((item) => item.verification?.ok === false).length;
    summary.cambios_propuestos_o_aplicados = results.reduce((total, item) => total + (item.changes?.length || 0), 0);
  }
  const summaryLabels = { total: "Productos", updated: "Actualizados", dry_run: "Dry run", skipped: "Sin cambios", not_found: "No encontrados", ambiguous: "Ambiguos", invalid_data: "Datos inválidos", failed: "Fallidos", productos_verificados: "Verificados", fallos_verificacion: "Fallos de verificación", cambios_propuestos_o_aplicados: "Cambios" };
  document.querySelector("#strapi-products-summary").innerHTML = Object.entries(summary).map(([key, value]) => `<div class="pdp-summary-card"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(summaryLabels[key] || key)}</span></div>`).join("");
  document.querySelector("#strapi-products-results").innerHTML = results.map((item) => {
    const verification = item.verification || {};
    const verificationLabel = item.status === "DRY_RUN" ? "Dry run · sin escritura" : verification.ok === true ? "Verificado" : verification.ok === false ? "Falló verificación" : "No verificado";
    const changes = (item.changes || []).map((change) => `<div class="strapi-change-row"><strong>${escapeHtml(change.field)}</strong><span>${escapeHtml(change.action || "update")} · ${change.verified === true ? "verificado" : change.verified === false ? "no coincide" : "sin verificación"}</span><small>Antes: ${escapeHtml(JSON.stringify(change.before ?? null))}</small><small>Después: ${escapeHtml(JSON.stringify(change.after ?? null))}</small>${change.created_id != null ? `<small>ID creado: ${escapeHtml(change.created_id)}</small>` : ""}</div>`).join("");
    return `<details class="strapi-product-result"><summary><span><b>${escapeHtml(item.program)}</b><small>Fila ${escapeHtml(item.row_number)} · ${escapeHtml(item.status)} · ${escapeHtml(verificationLabel)}</small></span><span>${escapeHtml(item.changes?.length || 0)} cambios</span></summary><p>${escapeHtml(item.message || "")}</p>${changes ? `<div class="strapi-change-list">${changes}</div>` : "<small>Sin diferencias detectadas.</small>"}</details>`;
  }).join("") || "Sin resultados todavía.";
}

const FILE_COUNTRIES = {
  AR: "argentina", MX: "mexico", SV: "el-salvador", US: "usa", DO: "republica-dominicana",
  PA: "panama", BO: "bolivia", CL: "chile", CO: "colombia", EC: "ecuador", PE: "peru", PY: "paraguay",
};

export function initializeStrapiProductsModule({ api, showToast }) {
  const country = document.querySelector("#strapi-products-country");
  const file = document.querySelector("#strapi-products-file");
  const run = document.querySelector("#strapi-products-run");
  const status = document.querySelector("#strapi-products-status");
  const dryRun = document.querySelector("#strapi-products-dry-run");
  const descriptionRun = document.querySelector("#strapi-products-description-run");
  const fichasFile = document.querySelector("#strapi-products-fichas-file");
  const schemaModeInputs = [...document.querySelectorAll('input[name="strapi-products-schema-mode"]')];
  const schemaField = document.querySelector("#strapi-products-schema-field");
  const schemaFile = document.querySelector("#strapi-products-schema-file");
  if (!country || !file || !run) return;

  schemaModeInputs.forEach((input) => input.addEventListener("change", () => {
    const usesJson = schemaModeInputs.find((item) => item.checked)?.value === "json";
    if (schemaField) schemaField.hidden = !usesJson;
    if (!usesJson && schemaFile) schemaFile.value = "";
  }));

  api.strapiProductCountries().then((payload) => {
    country.innerHTML = '<option value="">Selecciona un país</option>';
    Object.entries(payload.countries || {}).forEach(([value, item]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = item.label;
      country.append(option);
    });
  }).catch((error) => { status.textContent = error.message; });

  file.addEventListener("change", () => {
    const match = file.files[0]?.name.match(/^\s*\[([A-Za-z]{2})\]/);
    const countryValue = match ? FILE_COUNTRIES[match[1].toUpperCase()] : null;
    if (countryValue) {
      country.value = countryValue;
      status.textContent = `País detectado desde el archivo: ${country.options[country.selectedIndex]?.textContent || countryValue}.`;
    } else {
      status.textContent = "El archivo debe comenzar con un código como [AR].";
    }
  });

  run.addEventListener("click", async () => {
    if (!file.files[0]) {
      showToast("Selecciona un archivo Excel.", "error");
      return;
    }
    if (!dryRun.checked && !window.confirm("La ejecución real modificará registros en Strapi. ¿Deseas continuar?")) return;
    run.disabled = true;
    status.textContent = dryRun.checked ? "Ejecutando DRY RUN..." : "Ejecutando cambios reales...";
    try {
      const job = await api.runStrapiProducts(file.files[0], country.value, dryRun.checked);
      let current;
      do {
        await new Promise((resolve) => setTimeout(resolve, 500));
        current = await api.strapiProductStatus(job.job_id);
      } while (current.status === "RUNNING");
      renderResults(current);
      status.textContent = `${current.status}: ${current.summary?.total ?? 0} filas procesadas.`;
      const download = document.querySelector("#strapi-products-download");
      download.hidden = !current.download_url;
      if (current.download_url) download.href = `${api.baseUrl}${current.download_url}`;
      showToast("Automatización de Strapi terminada.", "info");
    } catch (error) {
      status.textContent = error.message;
      showToast(error.message, "error");
    } finally {
      run.disabled = false;
    }
  });

  descriptionRun?.addEventListener("click", async () => {
    if (!file.files[0]) {
      showToast("Selecciona un archivo Excel.", "error");
      return;
    }
    const schemaMode = schemaModeInputs.find((item) => item.checked)?.value || "integrated";
    if (schemaMode === "json" && !schemaFile?.files[0]) {
      showToast("Selecciona el JSON del esquema Strapi.", "error");
      return;
    }
    if (!dryRun.checked && !window.confirm("La ejecución real aplicará en Strapi los cambios del plan PDP, que puede incluir descripciones, tabs, FAQ y relaciones. ¿Deseas continuar?")) return;
    descriptionRun.disabled = true;
    status.textContent = dryRun.checked ? "Extrayendo descripciones PDP en DRY RUN..." : "Cargando descripciones PDP en Strapi...";
    try {
      const job = await api.runStrapiDescriptions(file.files[0], fichasFile?.files[0] || null, schemaMode === "json" ? schemaFile.files[0] : null, dryRun.checked);
      let current;
      do {
        await new Promise((resolve) => setTimeout(resolve, 500));
        current = await api.strapiProductStatus(job.job_id);
      } while (current.status === "RUNNING");
      renderResults(current);
      status.textContent = `${current.status}: ${current.summary?.total ?? 0} filas procesadas · esquema ${current.schema_source === "json" ? "JSON" : "integrado"} (${current.schema_version || "sin versión"}).`;
      const download = document.querySelector("#strapi-products-download");
      download.hidden = !current.download_url;
      if (current.download_url) download.href = `${api.baseUrl}${current.download_url}`;
      showToast("Carga de descripciones PDP terminada.", "info");
    } catch (error) {
      status.textContent = error.message;
      showToast(error.message, "error");
    } finally {
      descriptionRun.disabled = false;
    }
  });
}
