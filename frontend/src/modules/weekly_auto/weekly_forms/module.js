"use strict";

const state = { file: null, mapping: null, jobId: null, pollTimer: null };

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function mount() {
  const view = document.querySelector("#view-weekly-auto");
  if (!view || document.querySelector("#weekly-forms-panel")) return;
  view.insertAdjacentHTML("beforeend", `
    <article class="panel" id="weekly-forms-panel" style="margin-top:18px;">
      <div class="panel-header">
        <div><p class="eyebrow accent">Weekly Forms</p><h3>Envío y verificación de formularios</h3>
        <p class="panel-subtitle">Lee Country, Nivel, Activo de Test, Location y Lead. Procesa 5 filas y descansa 60 segundos.</p></div>
        <span class="status-badge success">5 + PAUSA 60 S</span>
      </div>
      <div class="bot-fields">
        <label class="pdp-file-field full"><span>Excel de Weekly Forms (.xlsx)</span>
          <input id="weekly-forms-file" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" />
          <small id="weekly-forms-file-name">Selecciona la matriz QA.</small>
        </label>
        <label class="field"><span>Buscar el Lead en</span><select id="weekly-forms-destination">
          <option value="both">InConcert y Balanceador</option><option value="inconcert">Solo InConcert</option><option value="balanceador">Solo Balanceador</option>
        </select></label>
        <label class="field"><span>Navegador</span><select id="weekly-forms-browser">
          <option value="chrome">Google Chrome - Perfil QA</option><option value="chromium">Chromium aislado</option><option value="firefox">Firefox</option>
        </select></label>
        <label class="toggle-field full-toggle"><input id="weekly-forms-visible" type="checkbox" checked />
          <span><strong>Mostrar el navegador</strong><small>Permite observar cómo identifica, llena y envía cada formulario.</small></span>
        </label>
      </div>
      <div class="bot-flow-actions" style="margin-top:12px;">
        <div><button class="secondary-button" id="weekly-forms-analyze" type="button">Analizar Excel</button>
          <button class="secondary-button" id="weekly-forms-download" type="button" hidden>Descargar Excel actualizado</button></div>
        <div><button class="danger-button" id="weekly-forms-stop" type="button" hidden>Detener</button>
          <button class="primary-button" id="weekly-forms-run" type="button" disabled>Ejecutar Weekly Forms <span>→</span></button></div>
      </div>
      <div class="bot-run-status" id="weekly-forms-status">Carga y analiza el Excel para comenzar.</div>
      <pre class="bot-terminal" id="weekly-forms-terminal" aria-live="polite">[SISTEMA] Esperando Excel.</pre>
      <div id="weekly-forms-summary" class="pdp-summary" style="margin-top:12px;display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;"></div>
    </article>`);
}

function setTerminal(message) {
  const terminal = document.querySelector("#weekly-forms-terminal");
  if (!terminal) return;
  terminal.textContent = message;
  terminal.scrollTop = terminal.scrollHeight;
}

function renderJob(job) {
  const status = document.querySelector("#weekly-forms-status");
  const summary = document.querySelector("#weekly-forms-summary");
  const download = document.querySelector("#weekly-forms-download");
  if (!status || !summary) return;
  const running = job.status === "RUNNING";
  status.className = `bot-run-status ${running ? "running" : job.status === "PASS" ? "success" : job.status === "FAIL" ? "error" : ""}`;
  status.innerHTML = `<strong>${escapeHtml(job.status)}</strong><span>${escapeHtml(job.phase || job.summary || "")}</span>`;
  summary.innerHTML = [
    ["Procesadas", `${job.completed || 0}/${job.total || 0}`], ["Con Lead", job.success || 0],
    ["Sin completar", job.failed || 0], ["Fila actual", job.current_row || "—"],
    ["Tandas", job.completed_batches || 0], ["Tamaño", job.batch_size || 5],
  ].map(([label, value]) => `<div class="bot-summary-card"><strong>${escapeHtml(value)}</strong><span>${label}</span></div>`).join("");
  setTerminal([
    `[${job.status}] ${job.completed || 0}/${job.total || 0} filas`,
    `[FASE] ${job.phase || "Preparando"}`,
    job.current_program ? `[CASO] ${job.current_program}` : "",
    job.last_error ? `[DETALLE] ${job.last_error}` : "",
  ].filter(Boolean).join("\n"));
  if (download) download.hidden = !job.download_url;
}

async function watch(dependencies) {
  let stillRunning = true;
  const poll = async () => {
    try {
      const job = await dependencies.weeklyFormsStatus(state.jobId);
      renderJob(job);
      if (job.status !== "RUNNING") {
        stillRunning = false;
        window.clearInterval(state.pollTimer);
        state.pollTimer = null;
        document.querySelector("#weekly-forms-stop").hidden = true;
        document.querySelector("#weekly-forms-run").disabled = false;
        dependencies.showToast(
          job.status === "PASS" ? "Weekly Forms finalizó." : `Weekly Forms terminó: ${job.summary || job.status}`,
          job.status === "PASS" ? "info" : "error",
        );
      }
    } catch (error) {
      window.clearInterval(state.pollTimer);
      state.pollTimer = null;
      dependencies.showToast(`No se pudo consultar Weekly Forms: ${error.message}`, "error");
    }
  };
  await poll();
  if (stillRunning && state.jobId && !state.pollTimer) state.pollTimer = window.setInterval(poll, 1800);
}

function setup(dependencies) {
  const fileInput = document.querySelector("#weekly-forms-file");
  const analyze = document.querySelector("#weekly-forms-analyze");
  const run = document.querySelector("#weekly-forms-run");
  const stop = document.querySelector("#weekly-forms-stop");
  const download = document.querySelector("#weekly-forms-download");

  fileInput.addEventListener("change", () => {
    state.file = fileInput.files?.[0] || null;
    state.mapping = null;
    run.disabled = true;
    document.querySelector("#weekly-forms-file-name").textContent = state.file?.name || "Selecciona la matriz QA.";
  });

  analyze.addEventListener("click", async () => {
    if (!state.file) return dependencies.showToast("Selecciona primero el Excel de Weekly Forms.", "error");
    analyze.disabled = true;
    try {
      const preview = await dependencies.previewWeeklyFormsSpreadsheet(state.file);
      const sheet = preview.sheets?.[0];
      if (!sheet) throw new Error("No se encontraron Country, Activo de Test, Location y Lead.");
      state.mapping = sheet.mapping;
      run.disabled = false;
      const total = sheet.total_rows ?? sheet.rows?.length ?? 0;
      setTerminal(`[ANÁLISIS] ${total} filas pendientes detectadas en ${sheet.name}.\n[REGLA] 5 procesos + pausa de 60 segundos.`);
      dependencies.showToast(`${total} filas de Weekly Forms listas.`, "info");
    } catch (error) {
      dependencies.showToast(error.message, "error");
    } finally {
      analyze.disabled = false;
    }
  });

  run.addEventListener("click", async () => {
    if (!state.file || !state.mapping) return;
    run.disabled = true;
    stop.hidden = false;
    download.hidden = true;
    try {
      const visible = document.querySelector("#weekly-forms-visible").checked;
      const config = {
        name: "Weekly Forms", automation_module: "weekly_forms", environment: "production",
        dry_run: false, workflow_mode: "form_validation",
        lead_search_destination: document.querySelector("#weekly-forms-destination").value,
        browser: document.querySelector("#weekly-forms-browser").value,
        headless: !visible, keep_browser_open: false,
      };
      const job = await dependencies.runWeeklyFormsBatch(state.file, config, state.mapping);
      state.jobId = job.job_id;
      renderJob(job);
      await watch(dependencies);
    } catch (error) {
      run.disabled = false;
      stop.hidden = true;
      dependencies.showToast(error.message, "error");
    }
  });

  stop.addEventListener("click", async () => {
    if (!state.jobId) return;
    stop.disabled = true;
    try {
      await dependencies.cancelWeeklyForms(state.jobId);
      dependencies.showToast("Detención solicitada.", "info");
    } catch (error) {
      dependencies.showToast(error.message, "error");
    } finally {
      stop.disabled = false;
    }
  });

  download.addEventListener("click", () => {
    if (!state.jobId) return;
    const anchor = document.createElement("a");
    anchor.href = dependencies.weeklyFormsDownloadUrl(state.jobId);
    anchor.download = "weekly-forms-resultado.xlsx";
    anchor.click();
  });
}

export function initializeWeeklyFormsModule(dependencies) {
  mount();
  setup(dependencies);
}
