"use strict";

// Cliente acotado a las rutas del módulo de hreflangs.
const BASE_URL = ["http:", "https:"].includes(window.location.protocol)
  ? window.location.origin
  : window.desktop?.apiUrl || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  // Convierte errores HTTP a mensajes que el módulo puede mostrar sin revelar secretos.
  const response = await fetch(`${BASE_URL}/api/strapi/hreflangs${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.detail || `La API respondió con ${response.status}.`);
  return payload;
}

export const hreflangsApi = {
  // El estado de configuración contiene solo datos públicos, nunca el token.
  config: () => request("/config"),
  // Inicia una simulación o una aplicación explícita para un locale.
  run: (payload) => request("/run", { method: "POST", body: JSON.stringify(payload) }),
  // Consulta incremental del progreso del trabajo.
  status: (jobId, after = 0) => request(`/jobs/${encodeURIComponent(jobId)}?after=${after}`),
  // Construye el enlace al reporte alojado por el backend.
  reportUrl: (jobId) => `${BASE_URL}/api/strapi/hreflangs/jobs/${encodeURIComponent(jobId)}/download`,
};
