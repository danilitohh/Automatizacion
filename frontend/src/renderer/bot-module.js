"use strict";

// Controlador visual del Bot: formulario, pasos, validación y ejecución.
const STORAGE_KEY = "qa-automation.utel-inconcert-config";
const ACTIVE_SINGLE_JOB_KEY = "qa-automation.utel-inconcert-active-job";
const LAST_SINGLE_JOB_KEY = "qa-automation.utel-inconcert-last-job";
const ACTIVE_BATCH_JOB_KEY = "qa-automation.utel-inconcert-active-batch";
const LAST_BATCH_JOB_KEY = "qa-automation.utel-inconcert-last-batch";

const state = {
  config: {
    name: "QA UTEL + InConcert",
    environment: "sandbox",
    dry_run: true,
    country: "Ecuador",
    utel_url: "",
    inconcert_url: "",
    modality: "En linea",
    level: "Licenciatura",
    form_type: "lateral",
    program_selection_strategy: "first",
    program_name: "",
    submit_success_pattern: "Env\u00edo correcto|Pronto recibir\u00e1s informaci\u00f3n",
    submit_error_pattern: "Error al enviar|Contacta a soporte|error|invalido|inválido|obligatorio|requerido|fall",
    browser: "chromium",
    headless: true,
    keep_browser_open: false,
    lead: { name: "pending", email: "pending@testingUtel.com", phone: "900000000" },
  },
  activeJobId: null,
  pollTimer: null,
  workflowMode: "product_release",
};

const stageLabels = {
  utel_open: "Abrir UTEL",
  utel_navigation: "Navegar modalidad/nivel",
  utel_form: "Identificar formulario",
  utel_fill: "Rellenar formulario",
  utel_submit: "Enviar formulario",
  dry_run_stop: "Detener antes del envio",
  inconcert_open: "Abrir InConcert",
  inconcert_login: "Login InConcert",
  inconcert_contacts: "Abrir contactos",
  inconcert_search: "Buscar lead",
  lead_balancer_search: "Buscar lead en Balanceador",
  inconcert_manage: "Abrir Gestionar",
  inconcert_conversion: "Confirmar conversion",
  config: "Validar configuracion",
  startup: "Iniciar automatizacion",
};

function renderModuleShell() {
  const view = document.querySelector("#view-bot");
  view.innerHTML = `
    <div class="bot-breadcrumb"><span>Espacio de trabajo</span><b>/</b><strong>Bot de verificaciones</strong></div>
    <div class="section-intro bot-page-intro"><p class="eyebrow accent">Automatizacion UTEL</p><p class="muted">Automatiza y valida los envios de leads en UTEL + InConcert de forma rapida y confiable.</p></div>
    <article class="bot-hero"><div class="bot-hero-icon">◇</div><div><div class="bot-hero-title"><h3>Bot UTEL + InConcert</h3><span class="status-badge success">ACTIVO</span></div><p>Envia un lead de prueba en UTEL y valida automaticamente que llegue a InConcert con evento de conversion.</p></div><button class="secondary-button" id="bot-guide" type="button">Ver guia rapida</button></article>
    <div class="bot-layout">
      <article class="panel bot-config-panel">
        <div class="panel-header"><div><p class="eyebrow">Configuracion</p><h3>Define la verificacion</h3><p class="panel-subtitle">Configura los datos necesarios para ejecutar el caso.</p></div><span class="status-badge success">● PLAYWRIGHT</span></div>
        <div class="bot-fields">
          <label class="field full"><span>Nombre de la ejecucion</span><input id="bot-name" type="text" placeholder="QA UTEL + InConcert" /></label>
          <label class="field"><span>Pais</span><input id="bot-country" type="text" placeholder="Ecuador" /></label>
          <label class="field"><span>Formulario</span><select id="bot-form-type"><option value="lateral">LateralBLC</option><option value="tarjeta">TarjetaBLC</option><option value="footer">FooterBLC</option></select></label>
          <label class="field full bot-internal-field"><span>URL UTEL</span><input id="bot-utel-url" type="url" placeholder="Se carga desde el Excel segun el pais" /><small id="bot-utel-url-status">Selecciona una fila del Excel; tambien puedes escribirla manualmente.</small></label>
          <div class="field full"><span>Importar Excel</span><div class="file-action-row"><input id="bot-spreadsheet" type="file" accept=".xlsx" /><button class="secondary-button" id="bot-analyze-spreadsheet" type="button">Analizar Excel</button></div><small id="bot-spreadsheet-status">Adjunta el archivo y pulsa Analizar Excel para revisar sus columnas.</small><div id="bot-column-mapping"></div></div>
          <label class="field full"><span>Fila importada</span><select id="bot-spreadsheet-row"><option value="">Selecciona una fila después de analizar</option></select></label>
          <label class="field full"><span>URL InConcert</span><input id="bot-inconcert-url" type="url" placeholder="https://..." /></label>
          <label class="field"><span>Modalidad</span><input id="bot-modality" type="text" placeholder="En linea" /></label>
          <label class="field"><span>Nivel</span><input id="bot-level" type="text" placeholder="Licenciatura" /></label>
          <label class="field"><span>Entorno</span><select id="bot-environment"><option value="sandbox">Sandbox</option><option value="production">Producción</option></select></label>
          <label class="toggle-field"><input id="bot-dry-run" type="checkbox" checked /><span><strong>Dry run seguro</strong><small>Rellena el formulario sin enviar leads reales</small></span></label>
          <label class="field"><span>Estrategia de programa</span><select id="bot-program-strategy"><option value="exact_match">Coincidencia exacta</option><option value="first">Primer programa visible</option></select></label>
          <label class="field full"><span>Nombre exacto del programa</span><input id="bot-program-name" type="text" placeholder="Obligatorio con coincidencia exacta" /></label>
          <label class="field full"><span>Patron de confirmacion (opcional)</span><input id="bot-success-pattern" type="text" placeholder="Ej. gracias|exito" /></label>
          <label class="field full"><span>Patron de error</span><input id="bot-error-pattern" type="text" /></label>
          <label class="field"><span>Navegador</span><select id="bot-browser"><option value="chromium">Chromium aislado</option><option value="chrome">Google Chrome - Perfil QA</option><option value="firefox">Firefox</option><option value="webkit">WebKit</option></select></label>
          <label class="toggle-field"><input id="bot-headless" type="checkbox" checked /><span><strong>Ejecutar en segundo plano</strong><small>Sin controlar tu navegador de trabajo</small></span></label>
          <label class="toggle-field full-toggle"><input id="bot-keep-browser-open" type="checkbox" /><span><strong>Modo debug visible</strong><small>Muestra el navegador durante la ejecucion y lo deja abierto al final</small></span></label>
        </div>
        <div class="security-note"><span>i</span><p>Las credenciales de InConcert se leen desde .env como INCONCERT_USERNAME/INCONCERT_PASSWORD o CRM_USERNAME/CRM_PASSWORD. No se guardan en la interfaz.</p></div>
        <div class="bot-step-builder bot-generated-lead-hidden" aria-hidden="true">
          <div class="builder-heading"><div><p class="eyebrow">Lead de prueba</p><h3>Datos generados automaticamente</h3><p class="panel-subtitle">Se crean al ejecutar cada caso.</p></div><span class="step-hint">Sin contrasenas</span></div>
          <div class="bot-fields step-fields">
            <label class="field full"><span>Nombre de prueba</span><input id="bot-lead-name" type="text" readonly /></label>
            <label class="field"><span>Email de prueba</span><input id="bot-lead-email" type="email" readonly /></label>
            <label class="field"><span>Telefono de prueba</span><input id="bot-lead-phone" type="tel" readonly /></label>
          </div>
          <p class="muted">El nombre, email y teléfono se generan automáticamente al ejecutar cada caso (Danilo1, Danilo2...). Son datos sintéticos y no se deben usar para contactar personas.</p>
        </div>
      </article>
      <section class="bot-error-log-panel bot-error-log-panel--standalone">
        <div class="bot-error-log-heading"><div><p class="eyebrow">Diagnóstico</p><h4>Log exclusivo de errores</h4><small>Incluye fila, etapa, URL, selector, captura y mensaje técnico completo.</small></div><div><button class="secondary-button" id="bot-copy-errors" type="button" disabled>Copiar errores</button><button class="secondary-button" id="bot-download-errors" type="button" disabled>Descargar .txt</button></div></div>
        <pre class="bot-error-terminal" id="bot-error-terminal" aria-live="polite">Sin errores registrados en esta ejecución.</pre>
      </section>
      <article class="panel bot-flow-panel">
        <div class="panel-header"><div><p class="eyebrow">Resultado</p><h3>Seguimiento de ejecucion</h3><p class="panel-subtitle">Sigue en tiempo real el progreso del flujo.</p></div><span class="step-count">UTEL → InConcert</span></div>
        <div class="bot-validation" id="bot-validation">Completa los campos con * y pulsa <strong>Ejecutar prueba</strong>. En Dry run no necesitas URL ni credenciales de InConcert.</div>
        <div class="bot-run-status" id="bot-run-status">El flujo todavia no se ha ejecutado.</div>
        <div class="bot-flow-actions"><div><button class="secondary-button" id="bot-clear" type="button">Limpiar</button></div><div><button class="secondary-button" id="bot-save" type="button">Guardar</button><button class="secondary-button" id="bot-validate" type="button">Validar</button><button class="secondary-button" id="bot-batch-run" type="button" hidden>Ejecutar todas las filas</button><button class="secondary-button" id="bot-retry-errors" type="button" hidden>Reintentar errores</button><button class="danger-button" id="bot-stop" type="button" hidden>Detener ejecución</button><button class="primary-button" id="bot-run" type="button">Ejecutar prueba <span>-></span></button></div></div>
        <pre class="bot-terminal" id="bot-terminal" aria-live="polite">[sistema] Esperando el inicio de la ejecución...</pre>
        <div class="pdp-summary" id="bot-summary"></div>
        <div class="bot-steps-list" id="bot-stages-list"></div>
        <details class="bot-preview"><summary>Ver configuracion generada</summary><pre id="bot-preview">{}</pre></details>
      </article>
    </div>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function organizeBotForm() {
  const fields = document.querySelector(".bot-config-panel > .bot-fields");
  if (!fields) return;
  // Algunos controles (como el selector de Excel) viven en un div porque
  // contienen un botón adicional; todos deben moverse como un solo campo.
  const field = (id) => document.querySelector(`#${id}`)?.closest("label, .field") || null;
  const sections = document.createElement("div");
  sections.className = "bot-form-sections";
  sections.innerHTML = `
    <section class="bot-form-section"><div class="bot-section-heading"><span class="step-number">1</span><div><strong>Origen del caso</strong><small>Selecciona el país y carga la fila del Excel</small></div></div><div class="bot-fields" data-section="source"></div></section>
    <details class="bot-advanced"><summary>Opciones avanzadas <span>Solo necesarias para casos especiales</span></summary><div class="bot-fields" data-section="advanced"></div></details>`;
  const source = sections.querySelector('[data-section="source"]');
  const advanced = sections.querySelector('[data-section="advanced"]');
  const moveFields = (ids, target) => ids.forEach((id) => {
    const node = field(id);
    if (node) target.append(node);
  });
  moveFields(["bot-name", "bot-country", "bot-spreadsheet"], source);
  moveFields(["bot-spreadsheet-row", "bot-utel-url"], advanced);
  moveFields(["bot-modality", "bot-level", "bot-form-type", "bot-program-strategy", "bot-program-name", "bot-inconcert-url", "bot-environment", "bot-success-pattern", "bot-error-pattern", "bot-browser", "bot-dry-run", "bot-headless", "bot-keep-browser-open"], advanced);
  ["bot-modality", "bot-level", "bot-form-type", "bot-program-strategy", "bot-program-name", "bot-inconcert-url"].forEach((id) => field(id)?.classList.add("bot-internal-field"));
  const securityNote = document.querySelector(".security-note");
  if (securityNote) advanced.append(securityNote);
  fields.replaceWith(sections);
  ["bot-country", "bot-utel-url", "bot-modality", "bot-level"].forEach((id) => {
    const title = field(id).querySelector("span");
    if (title && !title.textContent.includes("*")) title.textContent += " *";
  });
}

function loadConfig() {
  try {
    const storedConfig = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (storedConfig?.lead) state.config = { ...state.config, ...storedConfig, lead: { ...state.config.lead, ...storedConfig.lead } };
    if (state.config.program_selection_strategy === "exact_match" && !state.config.program_name) state.config.program_selection_strategy = "first";
    if (!state.config.submit_success_pattern) state.config.submit_success_pattern = "Env\u00edo correcto|Pronto recibir\u00e1s informaci\u00f3n";
    if (!state.config.submit_error_pattern) state.config.submit_error_pattern = "Error al enviar|Contacta a soporte|error|invalido|inválido|obligatorio|requerido|fall";
  } catch {
    localStorage.removeItem(STORAGE_KEY);
  }
}

function readForm() {
  state.config.name = document.querySelector("#bot-name").value.trim();
  state.config.environment = document.querySelector("#bot-environment").value;
  state.config.dry_run = document.querySelector("#bot-dry-run").checked;
  state.config.country = document.querySelector("#bot-country").value.trim();
  state.config.utel_url = document.querySelector("#bot-utel-url").value.trim();
  state.config.inconcert_url = document.querySelector("#bot-inconcert-url").value.trim();
  state.config.modality = document.querySelector("#bot-modality").value.trim();
  state.config.level = document.querySelector("#bot-level").value.trim();
  state.config.form_type = document.querySelector("#bot-form-type").value;
  state.config.program_selection_strategy = document.querySelector("#bot-program-strategy").value;
  state.config.program_name = document.querySelector("#bot-program-name").value.trim();
  state.config.submit_success_pattern = document.querySelector("#bot-success-pattern").value.trim();
  state.config.submit_error_pattern = document.querySelector("#bot-error-pattern").value.trim();
  state.config.browser = document.querySelector("#bot-browser").value;
  state.config.headless = document.querySelector("#bot-headless").checked;
  state.config.keep_browser_open = document.querySelector("#bot-keep-browser-open").checked;
  state.config.lead = {
    name: document.querySelector("#bot-lead-name").value.trim() || "pending",
    email: document.querySelector("#bot-lead-email").value.trim(),
    phone: document.querySelector("#bot-lead-phone").value.trim(),
  };
}

function writeForm() {
  document.querySelector("#bot-name").value = state.config.name;
  document.querySelector("#bot-environment").value = state.config.environment;
  document.querySelector("#bot-dry-run").checked = state.config.dry_run;
  document.querySelector("#bot-country").value = state.config.country;
  document.querySelector("#bot-utel-url").value = state.config.utel_url;
  document.querySelector("#bot-inconcert-url").value = state.config.inconcert_url;
  document.querySelector("#bot-modality").value = state.config.modality;
  document.querySelector("#bot-level").value = state.config.level;
  document.querySelector("#bot-form-type").value = state.config.form_type;
  document.querySelector("#bot-program-strategy").value = state.config.program_selection_strategy;
  document.querySelector("#bot-program-name").value = state.config.program_name;
  document.querySelector("#bot-success-pattern").value = state.config.submit_success_pattern;
  document.querySelector("#bot-error-pattern").value = state.config.submit_error_pattern;
  document.querySelector("#bot-browser").value = state.config.browser;
  document.querySelector("#bot-headless").checked = state.config.headless;
  document.querySelector("#bot-keep-browser-open").checked = state.config.keep_browser_open;
  document.querySelector("#bot-lead-name").value = state.config.lead.name;
  document.querySelector("#bot-lead-email").value = state.config.lead.email;
  document.querySelector("#bot-lead-phone").value = state.config.lead.phone;
}

function saveConfig(showToast) {
  readForm();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.config));
  renderPreview();
  showToast("Configuracion UTEL guardada en este equipo.", "info");
}

function renderPreview() {
  const preview = document.querySelector("#bot-preview");
  const safeConfig = { ...state.config, lead: { ...state.config.lead } };
  preview.textContent = JSON.stringify(safeConfig, null, 2);
}

function setValidation(message, type = "") {
  const validation = document.querySelector("#bot-validation");
  validation.className = `bot-validation ${type}`;
  validation.textContent = message;
}

function validateConfig(showToast) {
  readForm();
  const workflowMode = state.workflowMode || "product_release";
  const urlFields = [["URL de UTEL", state.config.utel_url]];
  if (!state.config.dry_run && workflowMode !== "form_validation") urlFields.push(["URL de InConcert", state.config.inconcert_url]);
  if (workflowMode !== "form_validation" && state.config.program_selection_strategy === "exact_match" && !state.config.program_name) {
    setValidation("Indica el nombre exacto del programa o selecciona el primer programa visible.", "error");
    return null;
  }
  const missingFields = [
    ["nombre del bot", state.config.name],
    ...(workflowMode === "form_validation" ? [] : [["pais", state.config.country]]),
      ["email del lead", state.config.lead.email],
    ["telefono del lead", state.config.lead.phone],
  ].filter(([, value]) => !value);

  if (missingFields.length) {
    const message = `Falta completar ${missingFields[0][0]}.`;
    setValidation(message, "error");
    showToast(message, "error");
    return null;
  }
  const invalidUrl = urlFields.find(([, value]) => !/^https?:\/\//i.test(value));
  if (invalidUrl) {
    const message = `${invalidUrl[0]} debe comenzar con http:// o https://.`;
    setValidation(message, "error");
    showToast(message, "error");
    return null;
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(state.config.lead.email)) {
    const message = "El email del lead no tiene un formato valido.";
    setValidation(message, "error");
    showToast(message, "error");
    return null;
  }

  setValidation("Configuracion valida. El flujo puede ejecutarse en segundo plano.", "success");
  showToast("Configuracion validada correctamente.", "info");
  renderPreview();
  return JSON.parse(JSON.stringify(state.config));
}

function renderRunResult(result) {
  const status = document.querySelector("#bot-run-status");
  const passed = result.status === "PASS";
  status.className = `bot-run-status ${passed ? "success" : "error"}`;
  status.innerHTML = `<strong>${passed ? "FLUJO COMPLETADO" : "FLUJO FALLIDO"}</strong><span>${escapeHtml(result.summary)} · ${escapeHtml(String(result.duration_seconds))} s</span>`;
  renderStages(result.stages || []);
  renderSummary(result);
}

function renderSummary(result) {
  const summary = document.querySelector("#bot-summary");
  const statusLabel = (value) => ({ success: "EXITOSO", failed: "ERROR", pending: "PENDIENTE", skipped: "NO ENVIADO" })[value] || value;
  summary.innerHTML = [
    ["Pais", result.country],
    ["Modalidad", result.modality],
    ["Nivel", result.level],
    ["Envío del formulario", statusLabel(result.utel_submission)],
    ["Login InConcert", statusLabel(result.inconcert_login)],
    ["Lead", statusLabel(result.lead_found)],
    ["Conversion", statusLabel(result.conversion_found)],
  ].map(([label, value]) => `<div class="pdp-summary-card"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span>${label === "Envío del formulario" ? `<small>${escapeHtml(result.utel_submission_message || "Sin detalle")}</small>` : ""}</div>`).join("");
}

function renderBatchResults(job) {
  const summary = document.querySelector("#bot-summary");
  const results = job.results || [];
  if (!results.length) return;
  summary.innerHTML = `<div class="batch-result-list"><strong>Detalle de filas procesadas</strong>${results.map((item) => {
    const result = item.result || {};
    const failedStage = (result.stages || []).find((stage) => stage.status === "FAIL");
    const ok = result.status === "PASS";
    return `<div class="batch-result-item ${ok ? "success" : "error"}"><span>${ok ? "OK" : "ERROR"}</span><strong>Fila ${escapeHtml(item.row?.row_number)} · ${escapeHtml(item.row?.program_name || item.row?.level || "Sin programa")}</strong><small>${escapeHtml(ok ? result.summary : failedStage?.message || result.summary || "Error no especificado")}</small></div>`;
  }).join("")}</div>`;
}

function renderTerminal(lines) {
  const terminal = document.querySelector("#bot-terminal");
  if (!terminal) return;
  terminal.textContent = lines.join("\n");
  terminal.scrollTop = terminal.scrollHeight;
}

function appendTerminal(lines) {
  const terminal = document.querySelector("#bot-terminal");
  if (!terminal) return;
  const previous = terminal.textContent.trimEnd();
  terminal.textContent = [previous, ...lines].filter(Boolean).join("\n");
  terminal.scrollTop = terminal.scrollHeight;
}

export function buildErrorLog(job) {
  const failures = [];
  (job.results || []).forEach((item) => {
    const result = item.result || {};
    const failedStages = (result.stages || []).filter((stage) => stage.status === "FAIL");
    if (result.status === "FAIL" && !failedStages.length) {
      failedStages.push({ stage: "ejecucion", message: result.summary || "La ejecución falló sin detalle de etapa." });
    }
    failedStages.forEach((stage) => failures.push({ item, result, stage }));
  });
  if (job.status === "FAIL" && job.summary) {
    failures.push({
      item: { row: { row_number: job.current_row, level: job.current_program } },
      result: { dry_run: job.dry_run },
      stage: { stage: "lote", message: job.summary },
    });
  }
  if (!failures.length) return "";
  const lines = [
    "LOG EXCLUSIVO DE ERRORES - BOT UTEL",
    `Generado: ${new Date().toLocaleString("es-CO")}`,
    `Trabajo: ${job.job_id || "sin-id"}`,
    `Progreso: ${job.completed ?? failures.length}/${job.total ?? failures.length} · Errores: ${job.failed ?? failures.length}`,
    "=".repeat(80),
  ];
  failures.forEach(({ item, result, stage }, index) => {
    const row = item.row || {};
    lines.push(
      "",
      `ERROR ${index + 1}`,
      `Fila: ${row.row_number || "?"}`,
      `Hoja: ${row.sheet || "No disponible"}`,
      `Caso/Nivel: ${row.program_name || row.level || "Sin programa"}`,
      `País: ${row.country || result.country || "No disponible"}`,
      `Formulario: ${row.form_type || result.form_type || "No disponible"}`,
      `Modalidad: ${result.modality || "No disponible"}`,
      `Programa seleccionado: ${result.selected_program_name || "No seleccionado"}`,
      `Modo: ${result.dry_run ? "DRY RUN - SIN ENVÍO" : "ENVÍO REAL"}`,
      `URL de entrada: ${row.utel_url || "No disponible"}`,
      `Datos de prueba: ${result.lead_name || "-"} · ${result.lead_email || "-"} · ${result.lead_phone || "-"}`,
      `Etapa: ${stageLabels[stage.stage] || stage.stage}`,
      `URL al fallar: ${stage.url || "No disponible"}`,
      `Selector: ${stage.selector || "No disponible"}`,
      `Captura: ${stage.screenshot || "No disponible"}`,
      "Mensaje completo:",
      stage.message || result.summary || "Error no especificado",
      "-".repeat(80),
    );
  });
  return lines.join("\n");
}

function renderErrorLog(job) {
  const terminal = document.querySelector("#bot-error-terminal");
  if (!terminal) return;
  const content = buildErrorLog(job);
  terminal.textContent = content || "Sin errores registrados en esta ejecución.";
  terminal.dataset.log = content;
  terminal.scrollTop = terminal.scrollHeight;
  document.querySelector("#bot-copy-errors").disabled = !content;
  document.querySelector("#bot-download-errors").disabled = !content;
}

function renderBatchTerminal(job, running = false) {
  const now = new Date().toLocaleTimeString("es-CO", { hour12: false });
  const lines = [`[${now}] [LOTE] ${job.completed || 0}/${job.total || 0} filas procesadas · OK: ${job.success || 0} · ERROR: ${job.failed || 0}`];
  (job.results || []).forEach((item) => {
    const label = `Fila ${item.row?.row_number || "?"} · ${item.row?.program_name || item.row?.level || "Sin programa"}`;
    const result = item.result || {};
    if (result.lead_name || result.lead_email || result.lead_phone) {
      lines.push(`[${now}] [DATOS DE PRUEBA] ${label} · Nombre: ${result.lead_name || "-"} · Email: ${result.lead_email || "-"} · Teléfono: ${result.lead_phone || "-"}`);
    }
    (result.stages || []).forEach((stage) => lines.push(`[${now}] [${stage.status === "PASS" ? "OK" : "ERROR"}] ${label} · ${stageLabels[stage.stage] || stage.stage}: ${stage.message}`));
  });
  if (running && (job.current_lead_name || job.current_lead_email || job.current_lead_phone)) {
    lines.push(`[${now}] [DATOS DE PRUEBA] Fila ${job.current_row || "?"} · ${job.current_program || "Sin programa"} · Nombre: ${job.current_lead_name || "-"} · Email: ${job.current_lead_email || "-"} · Teléfono: ${job.current_lead_phone || "-"}`);
  }
  if (running && job.last_error) lines.push(`[${now}] [ERROR] Último error · ${job.current_program || ""}: ${job.last_error}`);
  if (running) lines.push(`[${now}] [SISTEMA] Ejecutando la siguiente fila...`);
  renderTerminal(lines);
}

function renderStages(stages) {
  const list = document.querySelector("#bot-stages-list");
  if (!stages.length) {
    list.innerHTML = `<div class="bot-empty"><div class="empty-icon">◇</div><strong>El flujo todavia no se ha ejecutado</strong><span>Aqui aparecera el detalle de cada etapa en tiempo real.</span></div>`;
    return;
  }
  list.innerHTML = stages.map((stage) => {
    const ok = stage.status === "PASS";
    const stateLabel = ok ? "Completado" : "Error";
    return `<details class="utel-stage ${ok ? "success" : "error"}" ${ok ? "" : "open"}>
      <summary><span class="stage-marker">${escapeHtml(stage.step_number)}</span><span class="status-badge ${ok ? "success" : "error"}">${stateLabel}</span><strong>${escapeHtml(stageLabels[stage.stage] || stage.stage)}</strong><span>${escapeHtml(stage.message)}</span></summary>
      <div class="utel-stage-detail">
        <span>URL: ${escapeHtml(stage.url || "No disponible")}</span>
        <span>Selector: ${escapeHtml(stage.selector || "No aplica")}</span>
        <span>Screenshot: ${escapeHtml(stage.screenshot || "No generado")}</span>
      </div>
    </details>`;
  }).join("");
}

async function pollJob(showToast, statusApi, jobId) {
  try {
    const job = await statusApi(jobId);
    if (job.status === "RUNNING" || job.status === "QUEUED") {
      const status = document.querySelector("#bot-run-status");
      status.className = "bot-run-status running";
      status.innerHTML = `<strong>FLUJO EN SEGUNDO PLANO</strong><span>${escapeHtml(job.summary || "Playwright esta ejecutando UTEL e InConcert.")}</span><small>ID de ejecucion: ${escapeHtml(job.job_id)}</small>`;
      renderTerminal([`[${new Date().toLocaleTimeString("es-CO", { hour12: false })}] [SISTEMA] ${job.summary || "Ejecutando flujo UTEL/InConcert..."}`]);
      return;
    }
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
    state.activeJobId = null;
    localStorage.removeItem(ACTIVE_SINGLE_JOB_KEY);
    localStorage.setItem(LAST_SINGLE_JOB_KEY, jobId);
    document.querySelector("#bot-run").disabled = false;
    document.querySelector("#bot-stop")?.setAttribute("hidden", "");
    document.querySelector("#bot-run").classList.remove("loading");
    document.querySelector("#bot-run").innerHTML = "Ejecutar prueba <span>-></span>";
    if (job.result) renderRunResult(job.result);
    if (job.result) renderErrorLog({
      job_id: job.job_id,
      completed: 1,
      total: 1,
      failed: job.result.status === "FAIL" ? 1 : 0,
      results: [{ row: { row_number: 1, level: job.result.level, country: job.result.country, form_type: job.result.form_type }, result: job.result }],
    });
    if (job.result) renderTerminal([
      `[DATOS DE PRUEBA] Nombre: ${job.result.lead_name || "-"} · Email: ${job.result.lead_email || "-"} · Teléfono: ${job.result.lead_phone || "-"}`,
      ...(job.result.stages || []).map((stage) => `[${stage.status === "PASS" ? "OK" : "ERROR"}] ${stageLabels[stage.stage] || stage.stage}: ${stage.message}`),
    ]);
    showToast(job.status === "PASS" ? "Flujo UTEL/InConcert completado." : "El flujo UTEL/InConcert termino con errores.", job.status === "PASS" ? "info" : "error");
  } catch (error) {
    const status = document.querySelector("#bot-run-status");
    status.className = "bot-run-status error";
    const retryHint = error.status === 404
      ? "No se encontró temporalmente el registro del job en memoria del backend. Probablemente regresará al retomar la sesión."
      : "El trabajo continúa en el backend; la página volverá a consultar automáticamente.";
    status.innerHTML = `<strong>RECONECTANDO CON LA EJECUCIÓN</strong><span>${escapeHtml(error.message)}</span><small>${retryHint}</small>`;
  }
}

async function executeBot(showToast, runApi, statusApi) {
  if (state.activeJobId) {
    showToast("Ya hay un flujo UTEL/InConcert en ejecucion.", "error");
    return;
  }
  const config = validateConfig(showToast);
  if (!config) return;
  renderTerminal([`[${new Date().toLocaleTimeString("es-CO", { hour12: false })}] [SISTEMA] Iniciando una nueva ejecucion...`]);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));

  const runButton = document.querySelector("#bot-run");
  const status = document.querySelector("#bot-run-status");
  runButton.disabled = true;
  document.querySelector("#bot-stop")?.removeAttribute("hidden");
  runButton.classList.add("loading");
  runButton.innerHTML = "<span>◌</span> Ejecutando...";
  status.className = "bot-run-status running";
  status.innerHTML = "<strong>INICIANDO FLUJO</strong><span>Validando configuracion y creando trabajo en segundo plano.</span>";

  try {
    const job = await runApi(config);
    if (job.lead_name && job.lead_email && job.lead_phone) {
      state.config.lead.name = job.lead_name;
      state.config.lead.email = job.lead_email;
      state.config.lead.phone = job.lead_phone;
      writeForm();
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state.config));
      renderPreview();
      showToast(`Datos generados: ${job.lead_email}`, "info");
    }
    state.activeJobId = job.job_id;
    localStorage.setItem(ACTIVE_SINGLE_JOB_KEY, job.job_id);
    localStorage.removeItem(LAST_SINGLE_JOB_KEY);
    status.innerHTML = `<strong>FLUJO EN SEGUNDO PLANO</strong><span>Puedes seguir usando la app mientras se ejecuta.</span><small>ID de ejecucion: ${escapeHtml(job.job_id)}</small>`;
    state.pollTimer = window.setInterval(() => pollJob(showToast, statusApi, job.job_id), 1000);
    showToast("Flujo UTEL/InConcert iniciado.", "info");
  } catch (error) {
    status.className = "bot-run-status error";
    status.innerHTML = `<strong>NO SE PUDO EJECUTAR</strong><span>${escapeHtml(error.message)}</span>`;
    showToast(`No se pudo ejecutar: ${error.message}`, "error");
  } finally {
    if (!state.activeJobId) {
      runButton.disabled = false;
      runButton.classList.remove("loading");
      runButton.innerHTML = "Ejecutar prueba <span>-></span>";
    }
  }
}

export function initializeBotModule({ showToast, runUtelInconcertBot, utelInconcertStatus, cancelUtelInconcert, previewBotSpreadsheet, runUtelBatch, utelBatchStatus, cancelUtelBatch }) {
  renderModuleShell();
  organizeBotForm();
  loadConfig();
  writeForm();
  renderPreview();
  renderStages([]);

  const headlessToggle = document.querySelector("#bot-headless");
  const keepBrowserOpenToggle = document.querySelector("#bot-keep-browser-open");
  const spreadsheetInput = document.querySelector("#bot-spreadsheet");
  const spreadsheetRow = document.querySelector("#bot-spreadsheet-row");
  const analyzeSpreadsheetButton = document.querySelector("#bot-analyze-spreadsheet");
  const batchButton = document.querySelector("#bot-batch-run");
  const retryErrorsButton = document.querySelector("#bot-retry-errors");
  const stopButton = document.querySelector("#bot-stop");
  const copyErrorsButton = document.querySelector("#bot-copy-errors");
  const downloadErrorsButton = document.querySelector("#bot-download-errors");
  let spreadsheetFile = null;
  let selectedMapping = {};
  let batchTimer = null;
  let activeBatchJobId = null;
  let importedRows = [];
  let lastFinishedBatch = null;

  const stopBatchPolling = () => {
    if (batchTimer) window.clearInterval(batchTimer);
    batchTimer = null;
  };

  const pollBatchJob = async (jobId, announceCompletion = true) => {
    try {
      const current = await utelBatchStatus(jobId);
      const running = current.status === "RUNNING" || current.status === "QUEUED";
      const liveError = current.last_error ? ` · Último error: fila ${current.current_row} (${current.current_program}): ${current.last_error}` : "";
      const phase = current.phase ? `${current.phase} · ` : "";
      document.querySelector("#bot-run-status").textContent = `${phase}${current.dry_run ? "Dry run (sin envío)" : "Lote"}: ${current.completed}/${current.total} filas procesadas · OK: ${current.success} · Errores: ${current.failed}${liveError}`;
      renderBatchTerminal(current, running);
      renderErrorLog(current);

      if (running) return current;

      stopBatchPolling();
      activeBatchJobId = null;
      localStorage.removeItem(ACTIVE_BATCH_JOB_KEY);
      localStorage.setItem(LAST_BATCH_JOB_KEY, jobId);
      stopButton.hidden = true;
      batchButton.disabled = false;
      document.querySelector("#bot-run").disabled = false;
      lastFinishedBatch = current;
      const failedRows = (current.results || []).filter((item) => item.result?.status === "FAIL");
      retryErrorsButton.hidden = !spreadsheetFile || failedRows.length === 0;
      retryErrorsButton.disabled = failedRows.length === 0;
      retryErrorsButton.textContent = `Reintentar ${failedRows.length} error${failedRows.length === 1 ? "" : "es"}`;
      if (current.download_url) {
        const apiBase = window.desktop?.apiUrl || window.location.origin;
        const label = current.status === "PASS"
          ? (current.dry_run ? "Dry run completado (sin envío)" : "Lote completado")
          : "Lote finalizado con resultados parciales";
        document.querySelector("#bot-run-status").innerHTML = `${label}: ${current.success} OK, ${current.failed} con error. <a href="${apiBase}${current.download_url}" download>Descargar Excel actualizado</a>`;
        renderBatchResults(current);
        if (announceCompletion) showToast("Excel actualizado generado correctamente.", "info");
      } else {
        setValidation(current.summary || "El lote terminó con errores.", "error");
        if (announceCompletion) showToast(current.summary || "El lote terminó con errores.", "error");
      }
      return current;
    } catch (error) {
      const status = document.querySelector("#bot-run-status");
      if (error.status === 404) {
        // El backend guarda jobs solo en memoria. Si se reinició, un ID que
        // quedó en localStorage ya no representa un lote recuperable.
        stopBatchPolling();
        if (activeBatchJobId === jobId) activeBatchJobId = null;
        if (localStorage.getItem(ACTIVE_BATCH_JOB_KEY) === jobId) localStorage.removeItem(ACTIVE_BATCH_JOB_KEY);
        if (localStorage.getItem(LAST_BATCH_JOB_KEY) === jobId) localStorage.removeItem(LAST_BATCH_JOB_KEY);
        stopButton.hidden = true;
        batchButton.disabled = false;
        document.querySelector("#bot-run").disabled = false;
        status.className = "bot-run-status";
        const apiBase = window.desktop?.apiUrl || window.location.origin;
        status.innerHTML = `<strong>LOTE NO RECUPERABLE</strong><span>El backend se reinició y ya no conserva el estado en memoria.</span><a href="${apiBase}/api/bots/utel-inconcert/batch/${jobId}/download" download>Descargar Excel parcial, si ya fue generado</a><small>Los reportes guardados permanecen disponibles aunque el proceso se reinicie.</small>`;
        return null;
      }
      status.className = "bot-run-status error";
      status.innerHTML = `<strong>RECONECTANDO CON EL LOTE</strong><span>${escapeHtml(error.message)}</span><small>El trabajo continúa en el backend; la página volverá a consultar automáticamente.</small>`;
      return null;
    }
  };

  const watchBatchJob = async (jobId, { persist = true, announceCompletion = true } = {}) => {
    stopBatchPolling();
    activeBatchJobId = jobId;
    if (persist) {
      localStorage.setItem(ACTIVE_BATCH_JOB_KEY, jobId);
      localStorage.removeItem(LAST_BATCH_JOB_KEY);
    }
    stopButton.hidden = false;
    batchButton.disabled = true;
    document.querySelector("#bot-run").disabled = true;
    await pollBatchJob(jobId, announceCompletion);
    if (activeBatchJobId === jobId) {
      batchTimer = window.setInterval(() => void pollBatchJob(jobId), 1000);
    }
  };

  const watchSingleJob = async (jobId, { announce = true } = {}) => {
    state.activeJobId = jobId;
    const runButton = document.querySelector("#bot-run");
    runButton.disabled = true;
    runButton.classList.add("loading");
    runButton.innerHTML = "<span>◌</span> Ejecutando...";
    stopButton.hidden = false;
    await pollJob(announce ? showToast : () => {}, utelInconcertStatus, jobId);
    if (state.activeJobId === jobId) {
      state.pollTimer = window.setInterval(() => void pollJob(showToast, utelInconcertStatus, jobId), 1000);
    }
  };

  const restoreRememberedJob = async () => {
    const activeBatch = localStorage.getItem(ACTIVE_BATCH_JOB_KEY);
    if (activeBatch) {
      document.querySelector("#bot-run-status").innerHTML = "<strong>RECUPERANDO LOTE</strong><span>Consultando el progreso que continuó en segundo plano.</span>";
      await watchBatchJob(activeBatch, { persist: false, announceCompletion: false });
      if (activeBatchJobId === activeBatch) showToast("Ejecución por lote recuperada. Continúa en segundo plano.", "info");
      return;
    }

    const activeSingle = localStorage.getItem(ACTIVE_SINGLE_JOB_KEY);
    if (activeSingle) {
      document.querySelector("#bot-run-status").innerHTML = "<strong>RECUPERANDO EJECUCIÓN</strong><span>Consultando el progreso que continuó en segundo plano.</span>";
      await watchSingleJob(activeSingle, { announce: false });
      if (state.activeJobId === activeSingle) showToast("Ejecución recuperada. Continúa en segundo plano.", "info");
      return;
    }

    const lastBatch = localStorage.getItem(LAST_BATCH_JOB_KEY);
    if (lastBatch) {
      await watchBatchJob(lastBatch, { persist: false, announceCompletion: false });
      return;
    }

    const lastSingle = localStorage.getItem(LAST_SINGLE_JOB_KEY);
    if (lastSingle) await watchSingleJob(lastSingle, { announce: false });
  };
  copyErrorsButton.addEventListener("click", async () => {
    const content = document.querySelector("#bot-error-terminal")?.dataset.log || "";
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
      showToast("Log de errores copiado. Ya puedes pegarlo en el chat.", "info");
    } catch (error) {
      showToast(`No se pudo copiar el log: ${error.message}`, "error");
    }
  });
  downloadErrorsButton.addEventListener("click", () => {
    const content = document.querySelector("#bot-error-terminal")?.dataset.log || "";
    if (!content) return;
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `errores-utel-${new Date().toISOString().replaceAll(":", "-")}.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
    showToast("Log exclusivo de errores descargado.", "info");
  });
  const normalizeCountry = (value) => String(value || "").trim().toLocaleLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  const setMultiCountryMode = (enabled) => {
    const countryField = document.querySelector("#bot-country")?.closest("label, .field");
    if (countryField) countryField.classList.toggle("bot-internal-field", enabled);
    const sourceHint = document.querySelector('[data-section="source"]')?.closest("section")?.querySelector(".bot-section-heading small");
    if (sourceHint) {
      sourceHint.textContent = enabled
        ? "Los países y casos se toman de cada fila del Excel"
        : "Selecciona el país y carga la fila del Excel";
    }
  };
  const applyImportedRow = (row, index = null) => {
    if (!row) return;
    if (index !== null) spreadsheetRow.value = String(index);
    if (row.country) document.querySelector("#bot-country").value = row.country;
    if (row.modality) document.querySelector("#bot-modality").value = row.modality;
    if (row.level) document.querySelector("#bot-level").value = row.level;
    if (row.utel_url) {
      document.querySelector("#bot-utel-url").value = row.utel_url;
      document.querySelector("#bot-utel-url-status").textContent = "URL UTEL cargada desde la fila seleccionada del Excel.";
    }
    if (row.inconcert_url) document.querySelector("#bot-inconcert-url").value = row.inconcert_url;
    if (row.program_name) document.querySelector("#bot-program-name").value = row.program_name;
    if (row.form_type) {
      const location = row.form_type.toLowerCase();
      document.querySelector("#bot-form-type").value = location.includes("tarjeta") ? "tarjeta" : location.includes("footer") ? "footer" : "lateral";
    }
  };
  const renderColumnMapping = (headers, autoMapping = {}) => {
    const container = document.querySelector("#bot-column-mapping");
    const optionList = ['<option value="">Selecciona una columna</option>', ...headers.map((header) => `<option value="${escapeHtml(header)}">${escapeHtml(header)}</option>`)].join("");
    const findHeader = (key, fallback = "") => autoMapping[key] || headers.find((header) => normalizeCountry(header) === normalizeCountry(fallback)) || "";
    selectedMapping = {
      program_name: findHeader("program_name", "Programa"),
      modality: findHeader("modality", "Modalidad"),
      level: findHeader("level", "Nivel"),
      country: headers.find((header) => normalizeCountry(header) === "locale") || findHeader("country", "Country"),
      utel_url: findHeader("utel_url", "URL"),
      form_type: findHeader("form_type", "Location"),
      inconcert_url: findHeader("inconcert_url", "inconcert/balanceador") || findHeader("inconcert_url", "Url inconcert/balanceador"),
      lead_url: findHeader("lead_url", "URL LEAD") || "URL LEAD",
    };
    const isDeployValidation = !selectedMapping.program_name
      && Boolean(selectedMapping.level && selectedMapping.country && selectedMapping.form_type && selectedMapping.utel_url);
    selectedMapping.workflow_mode = isDeployValidation ? "form_validation" : "product_release";
    state.workflowMode = selectedMapping.workflow_mode;
    setMultiCountryMode(isDeployValidation);
    container.innerHTML = `<div class="mapping-title">Columnas a utilizar</div><div class="mapping-grid">
      <label><span>Programa *</span><select id="bot-map-program">${optionList}</select></label>
      <label><span>Modalidad</span><select id="bot-map-modality">${optionList}</select></label>
      <label><span>Nivel (alternativa)</span><select id="bot-map-level">${optionList}</select></label>
      <label><span>País (Locale/Country)</span><select id="bot-map-country">${optionList}</select></label>
      <label><span>URL *</span><select id="bot-map-url">${optionList}</select></label>
      <label><span>Formulario</span><select id="bot-map-form">${optionList}</select></label>
      <label><span>InConcert</span><select id="bot-map-inconcert">${optionList}</select></label>
      <label><span>Salida URL LEAD</span><select id="bot-map-lead">${optionList}<option value="URL LEAD">Crear columna URL LEAD</option></select></label>
    </div><small>Se detectaron ${headers.length} columnas. Puedes cambiar la selección manualmente.</small>`;
    document.querySelector("#bot-map-program").value = selectedMapping.program_name;
    document.querySelector("#bot-map-modality").value = selectedMapping.modality;
    document.querySelector("#bot-map-level").value = selectedMapping.level;
    document.querySelector("#bot-map-country").value = selectedMapping.country;
    document.querySelector("#bot-map-url").value = selectedMapping.utel_url;
    document.querySelector("#bot-map-form").value = selectedMapping.form_type;
    document.querySelector("#bot-map-inconcert").value = selectedMapping.inconcert_url;
    document.querySelector("#bot-map-lead").value = selectedMapping.lead_url || "URL LEAD";
    if (isDeployValidation) {
      ["bot-map-program", "bot-map-modality", "bot-map-lead"].forEach((id) => {
        document.querySelector(`#${id}`)?.closest("label")?.classList.add("bot-internal-field");
      });
      document.querySelector("#bot-map-level")?.closest("label")?.querySelector("span")?.replaceChildren("Nivel *");
      document.querySelector("#bot-map-inconcert")?.closest("label")?.querySelector("span")?.replaceChildren("InConcert/balanceador (opcional)");
      container.querySelector("small").textContent = "Flujo detectado: validacion de formularios por pais. Se reconocio la columna InConcert/balanceador; el Excel de salida incluira resultado y detalle.";
    }
    const updateAutomaticFields = () => {
      const visibility = {
        "bot-modality": isDeployValidation || Boolean(selectedMapping.modality),
        "bot-level": isDeployValidation || Boolean(selectedMapping.level),
        "bot-form-type": isDeployValidation || Boolean(selectedMapping.form_type),
        "bot-program-strategy": true,
        "bot-program-name": true,
        "bot-inconcert-url": true,
      };
      Object.entries(visibility).forEach(([id, hidden]) => document.querySelector(`#${id}`)?.closest("label, .field")?.classList.toggle("bot-internal-field", hidden));
    };
    updateAutomaticFields();
    ["program", "modality", "level", "country", "url", "form", "inconcert", "lead"].forEach((key) => document.querySelector(`#bot-map-${key}`).addEventListener("change", () => {
      const selectedRow = selectedMapping.selected_row_number;
      const selectedSheet = selectedMapping.selected_sheet;
      selectedMapping = { program_name: document.querySelector("#bot-map-program").value, modality: document.querySelector("#bot-map-modality").value, level: document.querySelector("#bot-map-level").value, country: document.querySelector("#bot-map-country").value, utel_url: document.querySelector("#bot-map-url").value, form_type: document.querySelector("#bot-map-form").value, inconcert_url: document.querySelector("#bot-map-inconcert").value, lead_url: document.querySelector("#bot-map-lead").value, workflow_mode: isDeployValidation ? "form_validation" : "product_release" };
      if (selectedRow !== undefined) selectedMapping.selected_row_number = selectedRow;
      if (selectedSheet !== undefined) selectedMapping.selected_sheet = selectedSheet;
      updateAutomaticFields();
    }));
  };
  const analyzeSpreadsheetFile = async (file) => {
    if (!file || !previewBotSpreadsheet) return;
    spreadsheetFile = file;
    analyzeSpreadsheetButton.disabled = true;
    analyzeSpreadsheetButton.textContent = "Analizando...";
    document.querySelector("#bot-spreadsheet-status").textContent = "Analizando hojas, columnas y filas...";
    try {
      const preview = await previewBotSpreadsheet(file);
      importedRows = preview.sheets.flatMap((sheet) => sheet.rows.map((row) => ({ ...row, sheet: sheet.name })));
      spreadsheetRow.innerHTML = '<option value="">Selecciona una fila</option>' + importedRows.map((row, index) => `<option value="${index}">${escapeHtml(row.sheet)} - fila ${row.row_number} - ${escapeHtml(row.program_name || row.level || row.utel_url || "sin nombre")}</option>`).join("");
      const firstSheet = preview.sheets[0];
      const allHeaders = [...new Set(preview.sheets.flatMap((sheet) => sheet.headers))];
      if (firstSheet) renderColumnMapping(allHeaders, firstSheet.mapping);
      batchButton.hidden = true;
      document.querySelector("#bot-run").textContent = selectedMapping.workflow_mode === "form_validation" ? "Ejecutar todos los casos" : "Ejecutar todos los programas";
      const currentCountry = normalizeCountry(document.querySelector("#bot-country").value);
      void currentCountry;
      document.querySelector("#bot-spreadsheet-status").textContent = `Excel analizado: ${allHeaders.length} columnas y ${importedRows.length} filas.${selectedMapping.workflow_mode === "form_validation" ? " Flujo Leads Deploy detectado." : ""}`;
      showToast("Excel analizado. Confirma las columnas y selecciona la fila.", "info");
    } catch (error) {
      setMultiCountryMode(false);
      document.querySelector("#bot-spreadsheet-status").textContent = "No se pudo analizar el Excel.";
      showToast(`No se pudo analizar el Excel: ${error.message}`, "error");
    } finally {
      analyzeSpreadsheetButton.disabled = false;
      analyzeSpreadsheetButton.textContent = "Analizar Excel";
    }
  };

  spreadsheetInput.addEventListener("change", async () => {
      const file = spreadsheetInput.files[0];
    if (!file || !previewBotSpreadsheet) return;
    spreadsheetFile = file;
    lastFinishedBatch = null;
    retryErrorsButton.hidden = true;
    if (spreadsheetInput.dataset.requestAnalyze !== "true") {
      importedRows = [];
      selectedMapping = {};
      state.workflowMode = "product_release";
      setMultiCountryMode(false);
      document.querySelector("#bot-column-mapping").innerHTML = "";
      batchButton.hidden = true;
      document.querySelector("#bot-spreadsheet-status").textContent = `Archivo listo: ${file.name}. Pulsa Analizar Excel para confirmar las columnas.`;
      return;
    }
    delete spreadsheetInput.dataset.requestAnalyze;
    try {
      const preview = await previewBotSpreadsheet(file);
      importedRows = preview.sheets.flatMap((sheet) => sheet.rows.map((row) => ({ ...row, sheet: sheet.name })));
      spreadsheetRow.innerHTML = '<option value="">Selecciona una fila</option>' + importedRows.map((row, index) => `<option value="${index}">${escapeHtml(row.sheet)} · fila ${row.row_number} · ${escapeHtml(row.program_name || row.level || row.utel_url || "sin nombre")}</option>`).join("");
      const fileSize = file.size > 1024 * 1024 ? `${(file.size / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(file.size / 1024))} KB`;
      document.querySelector("#bot-spreadsheet-status").textContent = `✓ ${file.name} · ${fileSize} · Archivo cargado`;
      const firstSheet = preview.sheets[0];
      const allHeaders = [...new Set(preview.sheets.flatMap((sheet) => sheet.headers))];
      if (firstSheet) renderColumnMapping(allHeaders, firstSheet.mapping);
      batchButton.hidden = true;
      showToast("Excel analizado. Selecciona la fila que deseas ejecutar.", "info");
    } catch (error) {
      showToast(`No se pudo analizar el Excel: ${error.message}`, "error");
    }
  });
  analyzeSpreadsheetButton.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (!spreadsheetInput.files[0]) {
      showToast("Selecciona primero un archivo .xlsx.", "error");
      return;
    }
    analyzeSpreadsheetButton.disabled = true;
    analyzeSpreadsheetButton.textContent = "Analizando...";
    document.querySelector("#bot-spreadsheet-status").textContent = "Analizando hojas, columnas y filas...";
    void analyzeSpreadsheetFile(spreadsheetInput.files[0]);
  });
  const executeBatch = async (mappingOverride = null, retryCount = 0) => {
    if (!spreadsheetFile || !runUtelBatch) return;
    readForm();
    const mappingToRun = mappingOverride || selectedMapping;
    if (!(mappingToRun.program_name || mappingToRun.level) || !mappingToRun.utel_url) {
      showToast("Selecciona Programa o Nivel, además de la columna URL.", "error");
      return;
    }
    const runButton = document.querySelector("#bot-run");
    renderTerminal([`[${new Date().toLocaleTimeString("es-CO", { hour12: false })}] [SISTEMA] Iniciando una nueva ejecucion por lote...`]);
    renderErrorLog({ results: [] });
    batchButton.disabled = true;
    retryErrorsButton.hidden = true;
    runButton.disabled = true;
    setValidation(retryCount
      ? `Reintento iniciado: se procesarán únicamente ${retryCount} fila${retryCount === 1 ? "" : "s"} con error.`
      : (state.config.dry_run ? "Dry run iniciado: se rellenarán las filas sin enviar leads." : "Lote iniciado. Se procesarán las filas una por una."), "success");
    try {
      const job = await runUtelBatch(spreadsheetFile, state.config, mappingToRun);
      await watchBatchJob(job.job_id);
    } catch (error) {
      batchButton.disabled = false;
      document.querySelector("#bot-run").disabled = false;
      setValidation(error.message, "error");
      showToast(error.message, "error");
    }
  };
  batchButton.addEventListener("click", executeBatch);
  retryErrorsButton.addEventListener("click", () => {
    const failedRows = (lastFinishedBatch?.results || [])
      .filter((item) => item.result?.status === "FAIL")
      .map((item) => ({ sheet: item.row?.sheet, row_number: item.row?.row_number }))
      .filter((row) => row.sheet && Number.isInteger(Number(row.row_number)));
    if (!spreadsheetFile || !failedRows.length) {
      showToast("No hay filas fallidas disponibles para reintentar. Vuelve a cargar el Excel si reiniciaste la página.", "error");
      return;
    }
    const retryMapping = { ...selectedMapping, selected_rows: failedRows };
    delete retryMapping.selected_sheet;
    delete retryMapping.selected_row_number;
    void executeBatch(retryMapping, failedRows.length);
  });
  stopButton.addEventListener("click", async () => {
    try {
      stopButton.disabled = true;
      if (activeBatchJobId && cancelUtelBatch) await cancelUtelBatch(activeBatchJobId);
      else if (state.activeJobId && cancelUtelInconcert) await cancelUtelInconcert(state.activeJobId);
      stopBatchPolling();
      if (state.pollTimer) window.clearInterval(state.pollTimer);
      state.pollTimer = null;
      activeBatchJobId = null;
      state.activeJobId = null;
      localStorage.removeItem(ACTIVE_BATCH_JOB_KEY);
      localStorage.removeItem(LAST_BATCH_JOB_KEY);
      localStorage.removeItem(ACTIVE_SINGLE_JOB_KEY);
      localStorage.removeItem(LAST_SINGLE_JOB_KEY);
      document.querySelector("#bot-run").disabled = false;
      document.querySelector("#bot-run").classList.remove("loading");
      stopButton.hidden = true;
      document.querySelector("#bot-run-status").textContent = "Ejecución detenida por el usuario.";
      appendTerminal([`[${new Date().toLocaleTimeString("es-CO", { hour12: false })}] [CANCELADO] Ejecución detenida por el usuario.`]);
      showToast("Ejecución detenida.", "info");
    } catch (error) {
      showToast(`No se pudo detener la ejecución: ${error.message}`, "error");
    } finally {
      stopButton.disabled = false;
    }
  });
  spreadsheetRow.addEventListener("change", () => {
    const row = importedRows[Number(spreadsheetRow.value)];
    if (row) {
      selectedMapping.selected_row_number = row.row_number;
      selectedMapping.selected_sheet = row.sheet;
    } else {
      delete selectedMapping.selected_row_number;
      delete selectedMapping.selected_sheet;
    }
    const runButton = document.querySelector("#bot-run");
    const label = row ? "Ejecutar fila seleccionada" : (selectedMapping.workflow_mode === "form_validation" ? "Ejecutar todos los casos" : "Ejecutar todos los programas");
    runButton.textContent = label;
    batchButton.textContent = row ? "Ejecutar fila seleccionada" : "Ejecutar todas las filas";
    applyImportedRow(row, Number.isNaN(Number(spreadsheetRow.value)) ? null : Number(spreadsheetRow.value));
    if (!row) return;
    if (row.country) document.querySelector("#bot-country").value = row.country;
    if (row.level) document.querySelector("#bot-level").value = row.level;
    if (row.utel_url) document.querySelector("#bot-utel-url").value = row.utel_url;
    if (row.inconcert_url) document.querySelector("#bot-inconcert-url").value = row.inconcert_url;
    if (row.program_name) document.querySelector("#bot-program-name").value = row.program_name;
    if (row.form_type) {
      const location = row.form_type.toLowerCase();
      document.querySelector("#bot-form-type").value = location.includes("tarjeta") ? "tarjeta" : location.includes("footer") ? "footer" : "lateral";
    }
  });
  // El país no selecciona filas automáticamente: una fila elegida es explícita;
  // si el selector queda vacío, el lote representa todos los programas.
  if (keepBrowserOpenToggle.checked) headlessToggle.checked = false;
  keepBrowserOpenToggle.addEventListener("change", () => {
    if (keepBrowserOpenToggle.checked) headlessToggle.checked = false;
  });
  headlessToggle.addEventListener("change", () => {
    if (headlessToggle.checked) keepBrowserOpenToggle.checked = false;
  });

  document.querySelector("#bot-save").addEventListener("click", () => saveConfig(showToast));
  document.querySelector("#bot-validate").addEventListener("click", () => validateConfig(showToast));
  document.querySelector("#bot-run").addEventListener("click", () => {
    if (spreadsheetFile) {
      if (!importedRows.length) {
        showToast("Analiza primero el Excel para ejecutar sus programas.", "error");
        return;
      }
      void executeBatch();
      return;
    }
    executeBot(showToast, runUtelInconcertBot, utelInconcertStatus);
  });
  document.querySelector("#bot-guide").addEventListener("click", () => showToast("1. Selecciona el pais. 2. Carga el Excel y elige una fila. 3. Confirma modalidad y nivel. 4. Ejecuta la prueba. Usa Dry run para validar sin enviar.", "info"));
  document.querySelector("#bot-clear").addEventListener("click", () => {
    localStorage.removeItem(STORAGE_KEY);
    state.workflowMode = "product_release";
    setMultiCountryMode(false);
    state.config = {
      name: "QA UTEL + InConcert",
      environment: "sandbox",
      dry_run: true,
      country: "Ecuador",
      utel_url: "",
      inconcert_url: "",
      modality: "En linea",
      level: "Licenciatura",
      form_type: "lateral",
      program_selection_strategy: "first",
      program_name: "",
      submit_success_pattern: "Env\u00edo correcto|Pronto recibir\u00e1s informaci\u00f3n",
      submit_error_pattern: "Error al enviar|Contacta a soporte|error|invalido|inválido|obligatorio|requerido|fall",
      browser: "chromium",
      headless: true,
      keep_browser_open: false,
      lead: { name: "pending", email: "pending@testingUtel.com", phone: "900000000" },
    };
    writeForm();
    renderPreview();
    renderStages([]);
    renderErrorLog({ results: [] });
    document.querySelector("#bot-summary").innerHTML = "";
    setValidation("Completa la configuracion para validar el flujo UTEL/InConcert.");
    showToast("Configuracion limpiada.", "info");
  });
  void restoreRememberedJob();
}
