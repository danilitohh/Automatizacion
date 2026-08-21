"use strict";

const API_BASE_URL = window.desktop?.apiUrl || "http://127.0.0.1:8000";

async function request(path) {
  const response = await fetch(`${API_BASE_URL}${path}`);
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
};
