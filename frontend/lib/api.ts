/**
 * Campus API client.
 *
 * Session-cookie auth, same-origin in production (behind Caddy), proxied in
 * dev. Every mutating request carries the CSRF token Django sets on
 * GET /api/auth/csrf/. No tokens are stored in the browser.
 */
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE && process.env.NODE_ENV === "development"
    ? process.env.NEXT_PUBLIC_API_BASE
    : "";

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`API ${status}`);
  }
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = readCookie("csrftoken");
    if (csrf) headers.set("X-CSRFToken", csrf);
  }

  const res = await fetch(`${API_BASE}/api${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
  });

  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}

export async function ensureCsrf(): Promise<void> {
  await api("/auth/csrf/");
}
