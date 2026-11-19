/**
 * Minimal API client for the GullyScore backend.
 *
 * The frontend is served by Flask as static files, so requests are same-origin
 * by default. Set `window.GULLY_API_BASE` (for example when the frontend is on
 * Vercel and the Flask API is elsewhere) or use a same-origin /api rewrite.
 */

import { scorerName } from "./prefs.js";

const API_BASE = String(window.GULLY_API_BASE || "").replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(message, { code = "api_error", status = 0, details = {} } = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

function csrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)gully_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function redirectToLogin() {
  if (window.location.pathname.endsWith("/login.html")) return;
  const next = `${window.location.pathname}${window.location.search}`;
  window.location.assign(`/pages/login.html?next=${encodeURIComponent(next)}`);
}

async function request(path, options = {}) {
  const headers = {
    "X-Actor": scorerName(),
    ...(options.headers || {}),
  };
  const token = csrfToken();
  if (token && options.method && options.method !== "GET") {
    headers["X-CSRF-Token"] = token;
  }

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      credentials: "include",
      headers,
    });
  } catch {
    throw new ApiError(
      navigator.onLine
        ? "Cannot reach the GullyScore API. Is the Flask server running?"
        : "You are offline. The score has been saved on this device.",
      { code: "network_error" },
    );
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (payload && payload.error) || {};
    if (response.status === 401 && !path.startsWith("/api/auth/")) {
      redirectToLogin();
    }
    throw new ApiError(error.message || `Request failed (${response.status})`, {
      code: error.code || "api_error",
      status: response.status,
      details: error.details || {},
    });
  }
  return payload ? payload.data : null;
}

export function apiGet(path) {
  return request(path, { headers: { Accept: "application/json" } });
}

/** Return the complete envelope, including pagination metadata. */
export async function apiGetPage(path) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { Accept: "application/json", "X-Actor": scorerName() },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (payload && payload.error) || {};
    if (response.status === 401) redirectToLogin();
    throw new ApiError(error.message || `Request failed (${response.status})`, {
      code: error.code || "api_error",
      status: response.status,
      details: error.details || {},
    });
  }
  return payload || { data: [], meta: {} };
}

export function apiPost(path, body) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

export function apiPatch(path, body) {
  return request(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

export function fetchHealth() {
  return apiGet("/api/health");
}

export function fetchPresets() {
  return apiGet("/api/rules/presets");
}
