export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export type ApiResult<T> = {ok: true; status: number; data: T} | {ok: false; status: number; data: unknown};

let csrfToken = "";

export function clearCsrf() {
  csrfToken = "";
}

export async function ensureCsrf() {
  if (csrfToken) return csrfToken;
  const response = await fetch(`${API_BASE}/api/auth/csrf/`, {credentials: "include"});
  if (!response.ok) throw new Error("csrf");
  const payload = await response.json() as {csrfToken: string};
  csrfToken = payload.csrfToken;
  return csrfToken;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<ApiResult<T>> {
  const headers = new Headers(options.headers);
  const method = (options.method || "GET").toUpperCase();
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  try {
    if (method !== "GET" && method !== "HEAD") headers.set("X-CSRFToken", await ensureCsrf());
    const response = await fetch(`${API_BASE}${path}`, {...options, headers, credentials: "include"});
    const text = await response.text();
    const data = text ? JSON.parse(text) as T : null;
    return response.ok
      ? {ok: true, status: response.status, data: data as T}
      : {ok: false, status: response.status, data};
  } catch {
    return {ok: false, status: 0, data: {detail: "Backend unavailable"}};
  }
}

export function apiError(data: unknown, fallback: string) {
  if (!data || typeof data !== "object") return fallback;
  const record = data as Record<string, unknown>;
  if (typeof record.detail === "string") return record.detail;
  const messages = Object.values(record).flatMap(value => Array.isArray(value) ? value.map(String) : typeof value === "string" ? [value] : []);
  return messages[0] || fallback;
}

export function resolveMedia(value: string) {
  if (!value) return "";
  if (value.startsWith("blob:") || value.startsWith("data:") || value.startsWith("http://") || value.startsWith("https://")) return value;
  if (value.startsWith("/media/")) return `${API_BASE}${value}`;
  return value;
}

export async function fileFromBlob(url: string, name: string) {
  const blob = await fetch(url).then(response => response.blob());
  const type = blob.type || "image/png";
  const extension = type.includes("pdf") ? "pdf" : (type.split("/")[1] || "png").replace("jpeg", "jpg");
  const stem = name.replace(new RegExp(`\\.${extension}$`, "i"), "");
  return new File([blob], `${stem}.${extension}`, {type});
}
