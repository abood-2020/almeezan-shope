export function getApiBase(): string {
  if (typeof window !== "undefined" && window.location.hostname) {
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") {
      return `http://${host}:8000`;
    }
  }
  if (process.env.NEXT_PUBLIC_API_BASE_URL) {
    return process.env.NEXT_PUBLIC_API_BASE_URL.replace(/\/$/, "");
  }
  return "http://127.0.0.1:8000";
}

export const API_BASE = getApiBase();

export type ApiResult<T> = {ok: true; status: number; data: T} | {ok: false; status: number; data: unknown};

let csrfToken = "";

export function clearCsrf() {
  csrfToken = "";
}

export async function ensureCsrf() {
  if (csrfToken) return csrfToken;
  const response = await fetch(`${getApiBase()}/api/auth/csrf/`, {credentials: "include"});
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
    const response = await fetch(`${getApiBase()}${path}`, {...options, headers, credentials: "include"});
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
  const msg = messages[0];
  if (msg === "This field cannot be blank.") return "هذا الحقل مطلوب ولا يمكن تركه فارغاً";
  return msg || fallback;
}

export function resolveMedia(value: string) {
  if (!value) return "";
  if (value.startsWith("blob:") || value.startsWith("data:") || value.startsWith("http://") || value.startsWith("https://")) return value;
  if (value.startsWith("/media/")) return `${getApiBase()}${value}`;
  return value;
}

export async function downloadAuthorized(path: string, fallbackName: string) {
  const response = await fetch(`${API_BASE}${path}`, {credentials: "include"});
  if (!response.ok) throw new Error("export");
  const blob = await response.blob();
  const match = (response.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/);
  const name = match?.[1] || fallbackName;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function fileFromBlob(url: string, name: string) {
  const blob = await fetch(url).then(response => response.blob());
  const type = blob.type || "image/png";
  const extension = type.includes("pdf") ? "pdf" : (type.split("/")[1] || "png").replace("jpeg", "jpg");
  const stem = name.replace(new RegExp(`\\.${extension}$`, "i"), "");
  return new File([blob], `${stem}.${extension}`, {type});
}
