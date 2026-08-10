import type { Dataset, Run, Session } from "./types";

let csrfToken = "";

export function setCsrfToken(token: string) {
  csrfToken = token;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (options.method && options.method !== "GET" && csrfToken) headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(`/api${path}`, { ...options, headers, credentials: "include" });
  if (!response.ok) {
    let detail = "خطای غیرمنتظره‌ای رخ داد";
    try {
      const payload = await response.json();
      detail = typeof payload.detail === "string" ? payload.detail : detail;
    } catch {
      // Preserve the localized fallback.
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const authApi = {
  me: () => api<Session>("/auth/me"),
  login: (username: string, password: string) =>
    api<Session>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => api<void>("/auth/logout", { method: "POST" }),
  password: (current_password: string, new_password: string) =>
    api<Session>("/auth/password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }),
};

export async function uploadDataset(file: File): Promise<Dataset> {
  const body = new FormData();
  body.append("upload", file);
  return api<Dataset>("/datasets", { method: "POST", body });
}

export const runsApi = {
  list: () => api<Run[]>("/runs"),
  get: (id: string) => api<Run>(`/runs/${id}`),
  create: (payload: unknown) => api<Run>("/runs", { method: "POST", body: JSON.stringify(payload) }),
  start: (id: string) => api<Run>(`/runs/${id}/start`, { method: "POST" }),
  cancel: (id: string) => api<Run>(`/runs/${id}/cancel`, { method: "POST" }),
  delete: (id: string) => api<void>(`/runs/${id}`, { method: "DELETE" }),
};

export function formatDate(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatNumber(value?: number | null, digits = 0) {
  if (value == null) return "—";
  return new Intl.NumberFormat("fa-IR", { maximumFractionDigits: digits }).format(value);
}
