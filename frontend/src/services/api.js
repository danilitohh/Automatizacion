"use strict";

const API_BASE_URL = window.desktop?.apiUrl || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { ...(isFormData ? {} : { "Content-Type": "application/json" }), ...(options.headers || {}) },
  });
  let payload;

  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    throw new Error(payload?.detail || `La API respondió con ${response.status}.`);
  }

  return payload;
}

export const api = {
  baseUrl: API_BASE_URL,
  health: () => request("/api/health"),
  dashboardSummary: () => request("/api/dashboard/summary"),
  executions: (limit = 20) => request(`/api/executions?limit=${limit}`),
  runBot: (config) => request("/api/bots/run", { method: "POST", body: JSON.stringify(config) }),
  startBotRecorder: (config) => request("/api/bots/recorder/start", { method: "POST", body: JSON.stringify(config) }),
  botRecorderEvents: (sessionId) => request(`/api/bots/recorder/${sessionId}/events`),
  stopBotRecorder: (sessionId) => request(`/api/bots/recorder/${sessionId}/stop`, { method: "POST" }),
  aiProviders: () => request("/api/ai/providers"),
  aiGenerate: (payload) => request("/api/ai/generate", { method: "POST", body: JSON.stringify(payload) }),
  validatePdp: (excelFile, docxFile) => {
    const formData = new FormData();
    formData.append("excel_file", excelFile);
    formData.append("docx_file", docxFile);
    return request("/api/pdp/validate", { method: "POST", body: formData });
  },
  validatePdpSemantic: (sourceFile, url, useAi = true) => {
    const formData = new FormData();
    formData.append("source_file", sourceFile);
    formData.append("url", url);
    formData.append("use_ai", String(useAi));
    return request("/api/pdp/semantic-validate", { method: "POST", body: formData });
  },
};
