"use strict";

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function renderResults(job) {
  const summary = job.summary || {};
  document.querySelector("#strapi-products-summary").innerHTML = Object.entries(summary).map(([key, value]) => `<div class="pdp-summary-card"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(key)}</span></div>`).join("");
  document.querySelector("#strapi-products-results").innerHTML = (job.results || []).map((item) => `<div class="recent-item"><span><b>${escapeHtml(item.program)}</b><small>${escapeHtml(item.status)} · ${escapeHtml(item.message || item.new_canonical || "")}</small></span><small>fila ${escapeHtml(item.row_number)}</small></div>`).join("") || "Sin resultados todavía.";
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
  if (!country || !file || !run) return;

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
    if (!dryRun.checked && !window.confirm("La ejecución real modificará únicamente shortDescription y longDescription en Strapi. ¿Deseas continuar?")) return;
    descriptionRun.disabled = true;
    status.textContent = dryRun.checked ? "Extrayendo descripciones PDP en DRY RUN..." : "Cargando descripciones PDP en Strapi...";
    try {
      const job = await api.runStrapiDescriptions(file.files[0], dryRun.checked);
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
      showToast("Carga de descripciones PDP terminada.", "info");
    } catch (error) {
      status.textContent = error.message;
      showToast(error.message, "error");
    } finally {
      descriptionRun.disabled = false;
    }
  });
}
