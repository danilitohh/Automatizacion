"use strict";

// Inicia FastAPI para servir en un mismo origen la API y la interfaz web.
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
require('./ensure-setup')();

const projectDirectory = path.resolve(__dirname, "..");
const host = process.env.WEB_HOST || "127.0.0.1";
const port = Number(process.env.WEB_PORT || process.env.API_PORT || 8000);

if (!Number.isInteger(port) || port < 1 || port > 65535) {
  console.error("WEB_PORT debe ser un puerto válido entre 1 y 65535.");
  process.exit(1);
}

const venvPython = path.join(projectDirectory, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const python = process.env.PYTHON_COMMAND || (fs.existsSync(venvPython) ? venvPython : process.platform === "win32" ? "python" : "python3");
const browserHost = host === "0.0.0.0" || host === "::" ? "127.0.0.1" : host;
const webUrl = `http://${browserHost}:${port}`;

console.log(`UTEL QA Web disponible en ${webUrl}`);
const child = spawn(
  python,
  ["-m", "uvicorn", "app.main:app", "--host", host, "--port", String(port)],
  {
    cwd: path.join(projectDirectory, "backend"),
    env: {
      ...process.env,
      PYTHONUNBUFFERED: "1",
      API_HOST: host,
      API_PORT: String(port),
      API_URL: webUrl,
      QA_WEB_MODE: "1",
    },
    stdio: "inherit",
    windowsHide: true,
  },
);

function openBrowser() {
  let command;
  let args;
  if (process.platform === "win32") {
    command = "cmd.exe";
    args = ["/c", "start", "", webUrl];
  } else if (process.platform === "darwin") {
    command = "open";
    args = [webUrl];
  } else {
    command = "xdg-open";
    args = [webUrl];
  }

  const opener = spawn(command, args, { detached: true, stdio: "ignore", windowsHide: true });
  opener.once("error", () => console.warn(`No se pudo abrir el navegador automaticamente. Abre ${webUrl}`));
  opener.unref();
}

async function openWhenReady() {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline && child.exitCode === null) {
    try {
      const response = await fetch(`${webUrl}/api/health`);
      if (response.ok) {
        openBrowser();
        return;
      }
    } catch {
      // FastAPI aun esta iniciando.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  if (child.exitCode === null) console.warn(`Abre ${webUrl} cuando el servidor este listo.`);
}

void openWhenReady();

child.once("error", (error) => {
  console.error(`No se pudo iniciar el servidor web: ${error.message}`);
  process.exitCode = 1;
});

child.once("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
