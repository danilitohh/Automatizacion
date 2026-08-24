"use strict";

const STORAGE_KEY = "qa-automation.bot-config";
const KEEP_OPEN_MIGRATION_KEY = "qa-automation.keep-browser-open-default-v1";

const STEP_TYPES = {
  hover: { label: "Hacer hover", icon: "⌁", target: "Selector, rol o texto" },
  select: { label: "Seleccionar opción", icon: "▾", target: "Selector del campo", value: "Valor de la opción" },
  check: { label: "Marcar checkbox", icon: "☑", target: "Selector del checkbox" },
  uncheck: { label: "Desmarcar checkbox", icon: "☐", target: "Selector del checkbox" },
  goto: { label: "Abrir URL", icon: "↗", target: "URL" },
  click: { label: "Hacer click", icon: "⌁", target: "Selector, rol o texto" },
  fill: { label: "Rellenar campo", icon: "✎", target: "Selector o label", value: "Valor" },
  assert_text: { label: "Verificar texto", icon: "✓", target: "Selector o área", value: "Texto esperado" },
  assert_url: { label: "Verificar URL", icon: "◎", target: "URL esperada" },
  wait: { label: "Esperar", icon: "◷", value: "Milisegundos" },
  screenshot: { label: "Tomar screenshot", icon: "▧", value: "Nombre de evidencia" },
  scroll: { label: "Hacer scroll", icon: "↕", target: "window", value: "Posición vertical (px)" },
};

const state = {
  config: {
    name: "",
    url: "",
    browser: "chromium",
    headless: true,
    keep_browser_open: true,
    steps: [],
  },
};

const recorderState = {
  sessionId: null,
  pollTimer: null,
  eventCount: 0,
  baseSteps: [],
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function loadConfig() {
  try {
    const storedConfig = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (storedConfig && Array.isArray(storedConfig.steps)) {
      state.config = { ...state.config, ...storedConfig };
    }
    // Las configuraciones anteriores no tenían este comportamiento activado.
    // Lo activamos una vez para que las ejecuciones existentes queden abiertas
    // y se puedan verificar; después el usuario podrá desactivarlo si lo desea.
    if (localStorage.getItem(KEEP_OPEN_MIGRATION_KEY) !== "1") {
      state.config.keep_browser_open = true;
      localStorage.setItem(KEEP_OPEN_MIGRATION_KEY, "1");
    }
  } catch {
    // Si existe una configuración dañada, empezamos con una configuración vacía.
    localStorage.removeItem(STORAGE_KEY);
  }
}

function readForm() {
  state.config.name = document.querySelector("#bot-name").value.trim();
  state.config.url = document.querySelector("#bot-url").value.trim();
  state.config.browser = document.querySelector("#bot-browser").value;
  state.config.headless = document.querySelector("#bot-headless").checked;
  state.config.keep_browser_open = document.querySelector("#bot-keep-browser-open").checked;
}

function writeForm() {
  document.querySelector("#bot-name").value = state.config.name;
  document.querySelector("#bot-url").value = state.config.url;
  document.querySelector("#bot-browser").value = state.config.browser;
  document.querySelector("#bot-headless").checked = state.config.headless;
  document.querySelector("#bot-keep-browser-open").checked = state.config.keep_browser_open;
}

function stepSummary(step) {
  const target = step.target ? `Objetivo: ${step.target}` : "";
  const value = step.value ? `Valor: ${step.value}` : "";
  return [target, value].filter(Boolean).join(" · ") || "Sin parámetros adicionales";
}

function renderSteps() {
  const container = document.querySelector("#bot-steps-list");
  const count = document.querySelector("#bot-step-count");
  count.textContent = `${state.config.steps.length} ${state.config.steps.length === 1 ? "paso" : "pasos"}`;
  const continueButton = document.querySelector("#bot-continue-record");
  if (continueButton && !recorderState.sessionId) continueButton.disabled = !state.config.steps.length;

  if (!state.config.steps.length) {
    container.innerHTML = `<div class="bot-empty"><div class="empty-icon">＋</div><strong>Aún no hay pasos</strong><span>Agrega acciones para construir el flujo de verificación.</span></div>`;
    renderPreview();
    return;
  }

  container.innerHTML = state.config.steps.map((step, index) => {
    const definition = STEP_TYPES[step.type];
    const actionModeEditor = ["click", "hover"].includes(step.type)
      ? `<select class="step-type-editor" data-step-type-index="${index}" title="Elegir acción"><option value="click" ${step.type === "click" ? "selected" : ""}>Click</option><option value="hover" ${step.type === "hover" ? "selected" : ""}>Hover</option></select>`
      : ["check", "uncheck"].includes(step.type)
        ? `<select class="step-type-editor" data-step-type-index="${index}" title="Elegir acciÃ³n de checkbox"><option value="check" ${step.type === "check" ? "selected" : ""}>Marcar checkbox</option><option value="uncheck" ${step.type === "uncheck" ? "selected" : ""}>Desmarcar checkbox</option></select>`
        : "";
    const editableValue = ["fill", "select"].includes(step.type)
      ? `${step.target ? `<span>Objetivo: ${escapeHtml(step.target)}</span>` : ""}<label class="step-value-editor"><span>Valor a enviar</span><input data-step-value-index="${index}" type="text" value="${escapeHtml(step.value)}" placeholder="Escribe el valor para este campo" /></label>`
      : `<span>${escapeHtml(stepSummary(step))}</span>`;
    return `<div class="bot-step-item">
      <div class="bot-step-number">${index + 1}</div>
      <div class="bot-step-icon">${definition.icon}</div>
      <div class="bot-step-content"><strong>${definition.label}</strong>${actionModeEditor}${editableValue}</div>
      <div class="bot-step-actions">
        <button class="step-action" data-step-action="up" data-step-index="${index}" title="Subir paso" ${index === 0 ? "disabled" : ""}>↑</button>
        <button class="step-action" data-step-action="down" data-step-index="${index}" title="Bajar paso" ${index === state.config.steps.length - 1 ? "disabled" : ""}>↓</button>
        <button class="step-action danger" data-step-action="delete" data-step-index="${index}" title="Eliminar paso">×</button>
      </div>
    </div>`;
  }).join("");

  container.querySelectorAll("[data-step-action]").forEach((button) => {
    button.addEventListener("click", () => updateStepOrder(button.dataset.stepAction, Number(button.dataset.stepIndex)));
  });
  container.querySelectorAll("[data-step-type-index]").forEach((select) => {
    select.addEventListener("change", () => {
      const index = Number(select.dataset.stepTypeIndex);
      state.config.steps[index].type = select.value;
      renderSteps();
    });
  });
  container.querySelectorAll("[data-step-value-index]").forEach((input) => {
    input.addEventListener("input", () => {
      const index = Number(input.dataset.stepValueIndex);
      state.config.steps[index].value = input.value;
      renderPreview();
    });
  });
  renderPreview();
}

function renderPreview() {
  const preview = document.querySelector("#bot-preview");
  preview.textContent = JSON.stringify(state.config, null, 2);
}

function updateStepFields() {
  const type = document.querySelector("#bot-step-type").value;
  const definition = STEP_TYPES[type];
  const targetField = document.querySelector("#bot-step-target");
  const valueField = document.querySelector("#bot-step-value");
  const targetLabel = document.querySelector("#bot-step-target-label");
  const valueLabel = document.querySelector("#bot-step-value-label");

  targetField.disabled = !definition.target;
  valueField.disabled = !definition.value;
  targetField.placeholder = definition.target || "No aplica para este paso";
  valueField.placeholder = definition.value || "No aplica para este paso";
  targetLabel.textContent = definition.target || "Objetivo";
  valueLabel.textContent = definition.value || "Valor";
}

function addStep(showToast) {
  const type = document.querySelector("#bot-step-type").value;
  const target = document.querySelector("#bot-step-target").value.trim();
  const value = document.querySelector("#bot-step-value").value.trim();
  const definition = STEP_TYPES[type];

  if (definition.target && !target) {
    showToast(`El paso «${definition.label}» necesita un objetivo.`, "error");
    return;
  }
  if (definition.value && !value) {
    showToast(`El paso «${definition.label}» necesita un valor.`, "error");
    return;
  }
  if (type === "wait" && (!Number.isFinite(Number(value)) || Number(value) <= 0)) {
    showToast("El tiempo de espera debe ser un número mayor que cero.", "error");
    return;
  }

  state.config.steps.push({ type, target, value });
  document.querySelector("#bot-step-target").value = "";
  document.querySelector("#bot-step-value").value = "";
  renderSteps();
  showToast("Paso agregado al flujo.", "info");
}

function updateStepOrder(action, index) {
  const targetIndex = action === "up" ? index - 1 : index + 1;
  if (action === "delete") state.config.steps.splice(index, 1);
  if (action === "up" || action === "down") {
    if (targetIndex < 0 || targetIndex >= state.config.steps.length) return;
    [state.config.steps[index], state.config.steps[targetIndex]] = [state.config.steps[targetIndex], state.config.steps[index]];
  }
  renderSteps();
}

function validateConfig(showToast) {
  readForm();
  if (!state.config.name) return showToast("Escribe un nombre para el bot.", "error");
  if (!state.config.url) return showToast("Indica la URL inicial del bot.", "error");
  if (!/^https?:\/\//i.test(state.config.url)) return showToast("La URL debe comenzar con http:// o https://.", "error");
  if (!state.config.steps.length) return showToast("Agrega al menos un paso al flujo.", "error");
  const incompleteValueStep = state.config.steps.find((step) => ["fill", "select"].includes(step.type) && !String(step.value ?? "").trim());
  if (incompleteValueStep) {
    return showToast(`Completa el valor del paso «${STEP_TYPES[incompleteValueStep.type].label}».`, "error");
  }

  const validation = document.querySelector("#bot-validation");
  validation.className = "bot-validation success";
  validation.textContent = "✓ Configuración válida. El flujo está listo para conectarse al ejecutor Playwright.";
  showToast("Flujo validado correctamente.", "info");
  return { ...state.config, steps: state.config.steps.map((step) => ({ ...step })) };
}

function saveConfig(showToast) {
  readForm();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.config));
  showToast("Configuración guardada en este equipo.", "info");
}

function renderRunResult(result) {
  const status = document.querySelector("#bot-run-status");
  const passed = result.status === "PASS";
  const stepSummary = result.steps.map((step) => `${step.status === "PASS" ? "✓" : "✕"} Paso ${step.step_number}: ${escapeHtml(step.message)}`).join("<br />");
  status.className = `bot-run-status ${passed ? "success" : "error"}`;
  status.innerHTML = `<strong>${passed ? "BOT COMPLETADO" : "BOT FALLIDO"}</strong><span>${escapeHtml(result.summary)} · ${escapeHtml(String(result.duration_seconds))} s</span><small>${stepSummary}</small>`;
}

async function executeBot(showToast, runBot) {
  const config = validateConfig(showToast);
  if (!config) return;

  saveConfig(() => {});
  const runButton = document.querySelector("#bot-run");
  const status = document.querySelector("#bot-run-status");
  runButton.disabled = true;
  runButton.classList.add("loading");
  status.className = "bot-run-status running";
  status.innerHTML = "<strong>EJECUTANDO BOT</strong><span>Playwright está realizando los pasos. Esta ventana puede seguir utilizándose.</span>";

  try {
    const result = await runBot(config);
    renderRunResult(result);
    showToast(result.status === "PASS" ? "Bot completado correctamente." : "El bot terminó con errores.", result.status === "PASS" ? "info" : "error");
  } catch (error) {
    status.className = "bot-run-status error";
    status.innerHTML = `<strong>NO SE PUDO EJECUTAR</strong><span>${escapeHtml(error.message)}</span>`;
    showToast(`No se pudo ejecutar el bot: ${error.message}`, "error");
  } finally {
    runButton.disabled = false;
    runButton.classList.remove("loading");
  }
}

function setRecordingStatus(active, message) {
  const button = document.querySelector("#bot-record");
  const status = document.querySelector("#bot-run-status");
  button.classList.toggle("recording", active);
  const stopButton = document.querySelector("#bot-stop-record");
  const continueButton = document.querySelector("#bot-continue-record");
  const hasDedicatedControls = Boolean(stopButton && continueButton);
  button.innerHTML = hasDedicatedControls
    ? '<span class="record-dot"></span> Grabar pasos'
    : (active ? '<span class="record-dot"></span> Detener grabación' : '<span class="record-dot"></span> Grabar pasos');
  button.disabled = hasDedicatedControls && active;
  if (stopButton) stopButton.disabled = !active;
  if (continueButton) continueButton.disabled = active || !state.config.steps.length;
  if (active) {
    status.className = "bot-run-status recording";
    status.innerHTML = `<strong>GRABANDO PASOS</strong><span>${escapeHtml(message)}</span>`;
  } else {
    status.className = "bot-run-status";
    status.textContent = "El bot todavía no se ha ejecutado.";
  }
}

function placeRecordingControls() {
  const actionGroup = document.querySelector(".bot-flow-actions > div:first-child");
  const stopButton = document.querySelector("#bot-stop-record");
  const continueButton = document.querySelector("#bot-continue-record");
  const controlsPanel = document.querySelector(".recording-controls");
  if (!actionGroup || !stopButton || !continueButton) return;
  actionGroup.append(stopButton, continueButton);
  controlsPanel?.remove();
}

async function pollRecorder(showToast, recorderApi) {
  if (!recorderState.sessionId) return;
  try {
    const response = await recorderApi.botRecorderEvents(recorderState.sessionId);
    const newEvents = response.events.slice(recorderState.eventCount);
    newEvents.forEach((event) => state.config.steps.push({ type: event.type, target: event.target, value: event.value || "" }));
    recorderState.eventCount = response.events.length;
    if (newEvents.length) renderSteps();
    if (!response.active) {
      clearInterval(recorderState.pollTimer);
      recorderState.pollTimer = null;
      recorderState.sessionId = null;
      setRecordingStatus(false, "");
      showToast("La grabación terminó.", "info");
    }
  } catch (error) {
    clearInterval(recorderState.pollTimer);
    recorderState.pollTimer = null;
    showToast(`No se pudieron consultar los pasos grabados: ${error.message}`, "error");
  }
}

async function toggleRecorder(showToast, recorderApi, append = true) {
  if (recorderState.sessionId) {
    try {
      const result = await recorderApi.stopBotRecorder(recorderState.sessionId);
      clearInterval(recorderState.pollTimer);
      recorderState.pollTimer = null;
      recorderState.sessionId = null;
      const recordedEvents = result.steps[0]?.type === "goto" ? result.steps.slice(1) : result.steps;
      const initialStep = recorderState.baseSteps.length ? [] : result.steps.slice(0, 1);
      state.config.steps = [...recorderState.baseSteps, ...initialStep, ...recordedEvents];
      recorderState.baseSteps = [];
      renderSteps();
      setRecordingStatus(false, "");
      showToast("Pasos grabados y agregados al flujo.", "info");
    } catch (error) {
      showToast(`No se pudo detener la grabación: ${error.message}`, "error");
    }
    return;
  }

  readForm();
  if (!state.config.url || !/^https?:\/\//i.test(state.config.url)) {
    showToast("Indica una URL inicial válida antes de grabar.", "error");
    return;
  }

  try {
    recorderState.baseSteps = append ? state.config.steps.map((step) => ({ ...step })) : [];
    const result = await recorderApi.startBotRecorder({
      url: state.config.url,
      browser: state.config.browser,
      steps: append ? recorderState.baseSteps : [],
    });
    recorderState.sessionId = result.session_id;
    recorderState.eventCount = 0;
    setRecordingStatus(true, "Interactúa en el navegador que se abrió. Los clicks y campos seleccionados aparecerán aquí; el valor se definirá en la app.");
    recorderState.pollTimer = window.setInterval(() => pollRecorder(showToast, recorderApi), 500);
    showToast("Grabación iniciada. Interactúa con el navegador.", "info");
  } catch (error) {
    showToast(`No se pudo iniciar la grabación: ${error.message}`, "error");
  }
}

export function initializeBotModule({ showToast, runBot, recorderApi }) {
  loadConfig();
  writeForm();
  placeRecordingControls();
  const headlessToggle = document.querySelector("#bot-headless");
  const keepBrowserOpenToggle = document.querySelector("#bot-keep-browser-open");
  if (keepBrowserOpenToggle.checked) headlessToggle.checked = false;
  keepBrowserOpenToggle.addEventListener("change", () => {
    if (keepBrowserOpenToggle.checked) headlessToggle.checked = false;
  });
  headlessToggle.addEventListener("change", () => {
    if (headlessToggle.checked) keepBrowserOpenToggle.checked = false;
  });
  const stepTypeSelect = document.querySelector("#bot-step-type");
  const fillOption = stepTypeSelect.querySelector('option[value="fill"]');
  if (!stepTypeSelect.querySelector('option[value="check"]')) {
    [
      ["hover", "Hacer hover"],
      ["check", "Marcar checkbox"],
      ["uncheck", "Desmarcar checkbox"],
    ].forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      stepTypeSelect.insertBefore(option, fillOption);
    });
  }
  updateStepFields();
  renderSteps();

  document.querySelector("#bot-step-type").addEventListener("change", updateStepFields);
  document.querySelector("#bot-add-step").addEventListener("click", () => addStep(showToast));
  document.querySelector("#bot-validate").addEventListener("click", () => validateConfig(showToast));
  document.querySelector("#bot-run").addEventListener("click", () => executeBot(showToast, runBot));
  document.querySelector("#bot-record").addEventListener("click", () => toggleRecorder(showToast, recorderApi, false));
  document.querySelector("#bot-stop-record").addEventListener("click", () => toggleRecorder(showToast, recorderApi));
  document.querySelector("#bot-continue-record").addEventListener("click", () => toggleRecorder(showToast, recorderApi, true));
  document.querySelector("#bot-save").addEventListener("click", () => saveConfig(showToast));
  document.querySelector("#bot-clear").addEventListener("click", () => {
    state.config.steps = [];
    renderSteps();
    showToast("Se quitaron los pasos del flujo.", "info");
  });
}
