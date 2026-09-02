"use strict";

function escapeHtml(value) { return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;"); }
function fileDescription(file, extension) { if (!file) return `Aún no has seleccionado un ${extension}.`; const size = file.size < 1024 * 1024 ? `${Math.ceil(file.size / 1024)} KB` : `${(file.size / (1024 * 1024)).toFixed(1)} MB`; return `${file.name} · ${size}`; }
function sectionClass(status) { return { PASS: "pass", WARNING: "warning", FAIL: "fail", NO_DISPONIBLE: "na" }[status] || "na"; }
function sectionLabel(status) { return { PASS: "Coincide", WARNING: "Revisar", FAIL: "No coincide", NO_DISPONIBLE: "Sin referencia" }[status] || "No disponible"; }
function programStatusClass(status) { return { PASS: "success", WARNING: "warning", ERROR: "error" }[status] || "pending"; }

function renderLegacySection(name, section) { const coverage = section.status === "NO_DISPONIBLE" ? "Sin sección" : `${section.coverage ?? 0}% de coincidencia`; return `<div class="pdp-section ${sectionClass(section.status)}"><strong>${escapeHtml(name)}</strong><span>${sectionLabel(section.status)} · ${coverage}</span></div>`; }
function renderLegacyProgram(program) { const sections = [["Título", program.title], ["Descripción", program.description], ["Asignaturas", program.subjects], ["FAQ", program.faqs]]; const missing = sections.flatMap(([name, section]) => (section.missing || []).map((item) => `${name}: ${item}`)); return `<article class="pdp-program-result"><div class="pdp-program-header"><div><strong>${escapeHtml(program.program)}</strong><a href="${escapeHtml(program.url)}" target="_blank" rel="noreferrer">${escapeHtml(program.url)}</a></div><span class="status-badge ${programStatusClass(program.status)}">${escapeHtml(program.status)}</span></div><div class="pdp-section-grid">${sections.map(([name, section]) => renderLegacySection(name, section)).join("")}</div><details><summary>${escapeHtml(program.message)}</summary>${missing.length ? `<ul class="pdp-missing">${missing.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : "<span>Sin diferencias destacadas para este programa.</span>"}</details></article>`; }
function renderLegacyResult(result) { const status = document.querySelector("#pdp-run-status"); const summary = document.querySelector("#pdp-summary"); const list = document.querySelector("#pdp-results-list"); const data = result.summary; const hasDifferences = data.failed || data.errors || data.warnings; status.className = `pdp-run-status ${hasDifferences ? "warning" : "success"}`; status.textContent = hasDifferences ? "Validación terminada. Hay diferencias o programas que necesitan revisión." : "Validación terminada. Todas las secciones detectadas coinciden."; document.querySelector("#pdp-result-count").textContent = `${data.programs} ${data.programs === 1 ? "PDP" : "PDPs"}`; summary.innerHTML = [[data.programs, "PDPs revisadas"], [data.passed, "Sin diferencias"], [data.failed, "Secciones a revisar"], [data.errors, "Errores de URL"]].map(([value, label]) => `<div class="pdp-summary-card"><strong>${escapeHtml(value)}</strong><span>${label}</span></div>`).join(""); list.innerHTML = result.programs.map(renderLegacyProgram).join(""); }

const FINDING_LABELS = { MATCH_EXACTO: "Igual", MATCH_NORMALIZADO: "Igual · texto normalizado", DIFERENTE: "Diferente", FALTANTE: "Falta en la página", EXTRA: "Extra en la página", DUPLICADO: "Duplicado", POSIBLE_COINCIDENCIA: "Posible coincidencia", REVISION_MANUAL: "Revisión manual" };
const FINDING_CLASSES = { MATCH_EXACTO: "success", MATCH_NORMALIZADO: "success", DIFERENTE: "warning", FALTANTE: "error", EXTRA: "warning", DUPLICADO: "warning", POSIBLE_COINCIDENCIA: "warning", REVISION_MANUAL: "warning" };
const EQUAL_STATUSES = new Set(["MATCH_EXACTO", "MATCH_NORMALIZADO"]);

function findingCard(finding) { const className = FINDING_CLASSES[finding.status] || "pending"; const kind = finding.document_source?.type || finding.comparison_type || "Elemento"; return `<details class="pdp-semantic-finding ${className}"><summary><span class="status-badge ${className}">${FINDING_LABELS[finding.status] || escapeHtml(finding.status)}</span><strong>${escapeHtml(kind)}</strong><span>${escapeHtml(finding.expected || finding.actual || "Sin texto")}</span></summary><div class="pdp-finding-detail"><div><b>En el documento</b><p>${escapeHtml(finding.expected || "No existe en el documento")}</p></div><div><b>En la página</b><p>${escapeHtml(finding.actual || "No encontrado")}</p></div><small>Confianza: ${Math.round((finding.confidence || 0) * 100)}% · ${escapeHtml(finding.reason || "")}</small></div></details>`; }

function renderSectionGroup(sectionName, findings, index) { const id = `pdp-section-${index}`; const equalCount = findings.filter((finding) => EQUAL_STATUSES.has(finding.status)).length; const differentCount = findings.length - equalCount; return `<article class="pdp-finding-section" data-section-index="${index}"><button class="pdp-finding-section-header pdp-section-toggle" type="button" aria-expanded="false"><span class="pdp-section-heading"><span class="pdp-section-kicker">Sección · haz clic para ver el contenido</span><h4>${escapeHtml(sectionName)}</h4></span><span class="pdp-section-counts"><span class="equal">${equalCount} iguales</span><span class="different">${differentCount} por revisar</span></span><span class="pdp-section-chevron" aria-hidden="true">＋</span></button><div class="pdp-section-body"><div class="pdp-section-filters" role="tablist" aria-label="Filtrar ${escapeHtml(sectionName)}"><button class="pdp-filter active" data-filter="all" data-target="${id}" type="button">Todos <span>${findings.length}</span></button><button class="pdp-filter" data-filter="equal" data-target="${id}" type="button">Iguales <span>${equalCount}</span></button><button class="pdp-filter" data-filter="different" data-target="${id}" type="button">No iguales o faltantes <span>${differentCount}</span></button></div><div class="pdp-section-findings" id="${id}">${findings.map(findingCard).join("")}</div></div></article>`; }

function bindFindingFilters() {
  const sections = [...document.querySelectorAll(".pdp-finding-section")];
  sections.forEach((section) => {
    section.classList.remove("is-open");
    const header = section.querySelector(".pdp-section-toggle");
    if (!header) return;
    header.addEventListener("click", (event) => {
      event.preventDefault();
      const shouldOpen = !section.classList.contains("is-open");
      sections.filter((other) => other !== section).forEach((other) => { other.open = false; });
      sections.filter((other) => other !== section).forEach((other) => other.classList.remove("is-open"));
      section.classList.toggle("is-open", shouldOpen);
      sections.filter((other) => other !== section).forEach((other) => other.querySelector(".pdp-section-toggle")?.setAttribute("aria-expanded", "false"));
      header.setAttribute("aria-expanded", String(shouldOpen));
    });
  });
  document.querySelectorAll(".pdp-filter").forEach((button) => button.addEventListener("click", () => {
    const group = button.closest(".pdp-finding-section");
    group.querySelectorAll(".pdp-filter").forEach((item) => item.classList.toggle("active", item === button));
    const filter = button.dataset.filter;
    group.querySelectorAll(".pdp-semantic-finding").forEach((finding) => {
      const equal = finding.classList.contains("success");
      finding.hidden = filter === "equal" ? !equal : filter === "different" ? equal : false;
    });
  }));
}

function renderSemanticResult(result) {
  const summary = document.querySelector("#pdp-semantic-summary"); const list = document.querySelector("#pdp-semantic-results"); const status = document.querySelector("#pdp-semantic-status"); const data = result.summary || {};
  const cards = [[data.sections, "Secciones"], [data.exact_matches, "Iguales"], [data.different, "Diferentes"], [data.missing, "Faltantes"], [data.extra, "Extras"], [data.manual_review, "Revisión manual"]];
  summary.innerHTML = cards.map(([value, label]) => `<div class="pdp-summary-card"><strong>${escapeHtml(value ?? 0)}</strong><span>${label}</span></div>`).join(""); status.className = `pdp-run-status ${result.status === "PASS" ? "success" : "warning"}`; const ai = result.ai || {}; const provider = ai.successful_provider ? ` Proveedor usado: ${ai.successful_provider}.` : ""; status.textContent = result.status === "PASS" ? `Verificación completada: no se detectaron diferencias.${provider}` : `Verificación completada: revisa los hallazgos por sección.${provider}`;
  const groups = new Map(); (result.findings || []).forEach((finding) => { const section = (finding.section || "Sin sección").trim() || "Sin sección"; if (!groups.has(section)) groups.set(section, []); groups.get(section).push(finding); });
  list.innerHTML = groups.size ? [...groups.entries()].map(([section, findings], index) => renderSectionGroup(section, findings, index)).join("") : `<div class="bot-empty"><strong>No se encontraron diferencias.</strong><span>La página coincide con el documento en los elementos extraídos.</span></div>`; bindFindingFilters();
}

function renderPagination(container, page, totalPages, onChange) {
  if (!container) return;
  container.innerHTML = `<button data-page="${page - 1}" ${page === 1 ? "disabled" : ""}>Anterior</button>${Array.from({ length: totalPages }, (_, index) => `<button data-page="${index + 1}" class="${index + 1 === page ? "active" : ""}">${index + 1}</button>`).join("")}<button data-page="${page + 1}" ${page === totalPages ? "disabled" : ""}>Siguiente</button><span>Página ${page} de ${totalPages}</span>`;
  container.querySelectorAll("button[data-page]").forEach((button) => button.addEventListener("click", () => onChange(Number(button.dataset.page))));
}

let currentLegacyResult = null;
let currentModalFilter = "all";
function modalSection(name, section, filter) {
  const equal = ["PASS", "MATCH_EXACTO", "MATCH_NORMALIZADO"].includes(section.status);
  if ((filter === "equal" && !equal) || (filter === "different" && equal)) return "";
  const status = equal ? "pass" : section.status === "FAIL" ? "fail" : "warning";
  const expected = section.expected || section.expected_items || "Sin información";
  const found = section.found || section.found_items || section.coverage ? `${section.found || section.found_items || 0} elementos · ${section.coverage || 0}%` : "No encontrado";
  const missing = section.missing?.length ? `<p><strong>Por revisar:</strong> ${escapeHtml(section.missing.join(" · "))}</p>` : "";
  return `<section class="pdp-modal-section ${status}"><h4>${escapeHtml(name)} · ${equal ? "Igual" : "Por revisar"}</h4><p><strong>En el documento:</strong> ${escapeHtml(expected)}</p><p><strong>En la PDP:</strong> ${escapeHtml(found)}</p>${missing}</section>`;
}
function openLegacyModal(program) {
  const modal = document.querySelector("#pdp-product-modal"); const content = document.querySelector("#pdp-modal-content");
  const sections = [["Título", program.title], ["Descripción", program.description], ["Asignaturas", program.subjects], ["Preguntas frecuentes", program.faqs]];
  const render = () => { content.innerHTML = `<p class="eyebrow">Detalle del producto</p><h2 class="pdp-modal-title" id="pdp-modal-title">${escapeHtml(program.program)}</h2><a class="pdp-modal-url" href="${escapeHtml(program.url)}" target="_blank" rel="noreferrer">${escapeHtml(program.url)}</a><div class="pdp-modal-filters"><button class="pdp-modal-filter ${currentModalFilter === "all" ? "active" : ""}" data-modal-filter="all" type="button">Todos</button><button class="pdp-modal-filter ${currentModalFilter === "equal" ? "active" : ""}" data-modal-filter="equal" type="button">Iguales</button><button class="pdp-modal-filter ${currentModalFilter === "different" ? "active" : ""}" data-modal-filter="different" type="button">Diferentes o faltantes</button></div><div class="pdp-modal-sections">${sections.map(([name, section]) => modalSection(name, section, currentModalFilter)).join("") || "<p>No hay resultados para este filtro.</p>"}</div>`; content.querySelectorAll("[data-modal-filter]").forEach((button) => button.addEventListener("click", () => { currentModalFilter = button.dataset.modalFilter; render(); })); };
  currentModalFilter = "all"; render(); modal.hidden = false;
}

let legacyPage = 1;
function renderLegacyResultPaginated(result) {
  const status = document.querySelector("#pdp-run-status"); const summary = document.querySelector("#pdp-summary"); const list = document.querySelector("#pdp-results-list"); const pagination = document.querySelector("#pdp-pagination"); const data = result.summary; const hasDifferences = data.failed || data.errors || data.warnings;
  status.className = `pdp-run-status ${hasDifferences ? "warning" : "success"}`; status.textContent = hasDifferences ? "Validación terminada. Hay diferencias o programas que necesitan revisión." : "Validación terminada. Todas las secciones detectadas coinciden."; document.querySelector("#pdp-result-count").textContent = `${data.programs} ${data.programs === 1 ? "PDP" : "PDPs"}`; summary.innerHTML = [[data.programs, "PDPs revisadas"], [data.passed, "Sin diferencias"], [data.failed, "Secciones a revisar"], [data.errors, "Errores de URL"]].map(([value, label]) => `<div class="pdp-summary-card"><strong>${escapeHtml(value)}</strong><span>${label}</span></div>`).join("");
  currentLegacyResult = result; const items = result.programs || []; const pageSize = 2; const totalPages = Math.max(1, Math.ceil(items.length / pageSize)); legacyPage = Math.min(legacyPage, totalPages); const start = (legacyPage - 1) * pageSize; list.innerHTML = items.slice(start, start + pageSize).map(renderLegacyProgram).join(""); renderPagination(pagination, legacyPage, totalPages, (page) => { legacyPage = page; renderLegacyResult(result); });
}

let semanticPage = 1;
function renderSemanticResultPaginated(result) {
  const summary = document.querySelector("#pdp-semantic-summary"); const list = document.querySelector("#pdp-semantic-results"); const pagination = document.querySelector("#pdp-semantic-pagination"); const status = document.querySelector("#pdp-semantic-status"); const data = result.summary || {}; const cards = [[data.sections, "Secciones"], [data.exact_matches, "Iguales"], [data.different, "Diferentes"], [data.missing, "Faltantes"], [data.extra, "Extras"], [data.manual_review, "Revisión manual"]];
  summary.innerHTML = cards.map(([value, label]) => `<div class="pdp-summary-card"><strong>${escapeHtml(value ?? 0)}</strong><span>${label}</span></div>`).join(""); const ai = result.ai || {}; const provider = ai.successful_provider ? ` Proveedor usado: ${ai.successful_provider}.` : ""; status.className = `pdp-run-status ${result.status === "PASS" ? "success" : "warning"}`; status.textContent = result.status === "PASS" ? `Verificación completada: no se detectaron diferencias.${provider}` : `Verificación completada: revisa los hallazgos por sección.${provider}`;
  const groups = new Map(); (result.findings || []).forEach((finding) => { const section = (finding.section || "Sin sección").trim() || "Sin sección"; if (!groups.has(section)) groups.set(section, []); groups.get(section).push(finding); }); const items = [...groups.entries()]; const totalPages = Math.max(1, Math.ceil(items.length / 4)); semanticPage = Math.min(semanticPage, totalPages); const start = (semanticPage - 1) * 4; list.innerHTML = items.length ? items.slice(start, start + 4).map(([section, findings], index) => renderSectionGroup(section, findings, start + index)).join("") : `<div class="bot-empty"><strong>No se encontraron diferencias.</strong><span>La página coincide con el documento en los elementos extraídos.</span></div>`; renderPagination(pagination, semanticPage, totalPages, (page) => { semanticPage = page; renderSemanticResult(result); }); bindFindingFilters();
}

export function initializePdpModule({ showToast, validatePdp, validatePdpSemantic }) {
  renderLegacyResult = renderLegacyResultPaginated;
  renderSemanticResult = renderSemanticResultPaginated;
  document.querySelector("#pdp-results-list")?.addEventListener("click", (event) => { const card = event.target.closest(".pdp-program-result"); if (!card || event.target.closest("a, details")) return; const index = (legacyPage - 1) * 2 + [...card.parentElement.children].indexOf(card); if (currentLegacyResult?.programs[index]) openLegacyModal(currentLegacyResult.programs[index]); });
  document.querySelectorAll("[data-modal-close]").forEach((item) => item.addEventListener("click", () => { document.querySelector("#pdp-product-modal").hidden = true; }));
  const singleMode = document.querySelector("#pdp-mode-single"); const bulkMode = document.querySelector("#pdp-mode-bulk"); const singlePanel = document.querySelector("#pdp-single-panel"); const bulkPanel = document.querySelector("#pdp-bulk-panel");
  const selectMode = (mode) => { const single = mode === "single"; singlePanel.hidden = !single; bulkPanel.hidden = single; singleMode.classList.toggle("active", single); bulkMode.classList.toggle("active", !single); singleMode.setAttribute("aria-selected", String(single)); bulkMode.setAttribute("aria-selected", String(!single)); };
  singleMode?.addEventListener("click", () => selectMode("single")); bulkMode?.addEventListener("click", () => selectMode("bulk"));
  const excelInput = document.querySelector("#pdp-excel-file"); const docxInput = { files: [{ name: "documento-en-excel.docx" }] }; const excelName = document.querySelector("#pdp-excel-name"); const runButton = document.querySelector("#pdp-run"); const status = document.querySelector("#pdp-run-status");
  if (!excelInput || !excelName || !runButton || !status) return;
  excelInput.addEventListener("change", () => { excelName.textContent = fileDescription(excelInput.files[0], "Excel"); });
  runButton.addEventListener("click", async () => { const excelFile = excelInput.files[0]; const docxFile = docxInput.files[0]; if (!excelFile || !docxFile) return showToast("Selecciona el Excel y el DOCX antes de ejecutar la comparación.", "error"); if (!excelFile.name.toLowerCase().endsWith(".xlsx") || !docxFile.name.toLowerCase().endsWith(".docx")) return showToast("Los archivos deben tener extensiones .xlsx y .docx.", "error"); runButton.disabled = true; runButton.classList.add("loading"); status.className = "pdp-run-status running"; status.textContent = "Leyendo fuentes y revisando las páginas PDP. El tiempo depende de la cantidad de URLs."; try { renderLegacyResult(await validatePdp(excelFile, docxFile)); showToast("Validación de PDP terminada. Revisa las diferencias marcadas.", "info"); } catch (error) { status.className = "pdp-run-status error"; status.textContent = error.message; showToast(`No se pudo validar las PDP: ${error.message}`, "error"); } finally { runButton.disabled = false; runButton.classList.remove("loading"); } });
  const sourceInput = document.querySelector("#pdp-source-file"); const sourceName = document.querySelector("#pdp-source-name"); const pageUrl = document.querySelector("#pdp-page-url"); const useAi = document.querySelector("#pdp-use-ai"); const semanticRun = document.querySelector("#pdp-semantic-run"); const semanticStatus = document.querySelector("#pdp-semantic-status");
  if (!sourceInput || !sourceName || !pageUrl || !useAi || !semanticRun || !semanticStatus) return;
  sourceInput.addEventListener("change", () => { sourceName.textContent = fileDescription(sourceInput.files[0], "documento"); }); semanticRun.addEventListener("click", async () => { const sourceFile = sourceInput.files[0]; if (!sourceFile || !pageUrl.value.trim()) return showToast("Selecciona un documento y escribe la URL antes de comparar.", "error"); semanticRun.disabled = true; semanticRun.classList.add("loading"); semanticStatus.className = "pdp-run-status running"; semanticStatus.textContent = "Extrayendo la estructura del documento y de la página. Puede tardar unos segundos..."; try { renderSemanticResult(await validatePdpSemantic(sourceFile, pageUrl.value.trim(), useAi.checked)); showToast("Comparación terminada.", "info"); } catch (error) { semanticStatus.className = "pdp-run-status error"; semanticStatus.textContent = error.message; showToast(`No se pudo comparar: ${error.message}`, "error"); } finally { semanticRun.disabled = false; semanticRun.classList.remove("loading"); } });
}
