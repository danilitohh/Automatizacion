"use strict";

const { app, BrowserWindow } = require("electron");
const path = require("node:path");
const { spawn } = require("node:child_process");

let backendProcess;

function startBackend() {
  // Electron arranca FastAPI como proceso local para que el usuario no tenga que
  // abrir una terminal. Las dependencias de Python deben estar instaladas antes.
  const pythonCommand = process.env.PYTHON_COMMAND || (process.platform === "win32" ? "python" : "python3");
  const backendDirectory = path.resolve(__dirname, "../../backend");
  const backendArguments = ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "" + (process.env.API_PORT || "8000")];

  backendProcess = spawn(pythonCommand, backendArguments, {
    cwd: backendDirectory,
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });

  backendProcess.stdout.on("data", (data) => console.log(`[FastAPI] ${data}`));
  backendProcess.stderr.on("data", (data) => console.error(`[FastAPI] ${data}`));
  backendProcess.on("error", (error) => {
    console.error("No fue posible iniciar FastAPI:", error.message);
  });
  backendProcess.on("exit", (code) => {
    if (code && !app.isQuitting) {
      console.error(`FastAPI terminó con código ${code}.`);
    }
  });
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1100,
    minHeight: 720,
    backgroundColor: "#0b1220",
    title: "QA Automation",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  window.loadFile(path.resolve(__dirname, "../index.html"));
}

app.whenReady().then(() => {
  startBackend();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", () => {
  app.isQuitting = true;
  if (backendProcess && !backendProcess.killed) backendProcess.kill();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
