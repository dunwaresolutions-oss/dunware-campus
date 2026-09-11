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
  const isForm =
    typeof FormData !== "undefined" && init.body instanceof FormData;
  if (init.body && !isForm && !headers.has("Content-Type")) {
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
  let data: unknown = null;
  let unparseable = false;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      // Not JSON -- an HTML error page (Django's default 404/500 page, a
      // Caddy proxy error, a route the running backend doesn't know about
      // yet) rather than a DRF error body. Without this, JSON.parse's raw
      // exception ("Unexpected token '<' ... is not valid JSON") leaked
      // straight through to the UI instead of a readable message.
      unparseable = true;
    }
  }
  if (!res.ok) {
    throw new ApiError(
      res.status,
      unparseable
        ? {
            detail: `The server returned an error page (HTTP ${res.status}) instead of a normal response. It may be out of date, restarting, or misconfigured.`,
          }
        : data,
    );
  }
  if (unparseable) {
    throw new ApiError(res.status, {
      detail: "The server sent back something unexpected, not data.",
    });
  }
  return data as T;
}

export async function ensureCsrf(): Promise<void> {
  await api("/auth/csrf/");
}
