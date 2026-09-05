/** Small display helpers shared across the console. */

export const money = (cents: number | null | undefined): string =>
  cents == null
    ? "—"
    : (cents / 100).toLocaleString(undefined, {
        style: "currency",
        currency: "CAD",
      });

export const date = (v: string | null | undefined): string =>
  v ? new Date(v).toLocaleDateString(undefined, { dateStyle: "medium" }) : "—";

export const datetime = (v: string | null | undefined): string =>
  v
    ? new Date(v).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";

export const time = (v: string | null | undefined): string => {
  if (!v) return "—";
  // "HH:MM[:SS]" or an ISO datetime
  const m = /^(\d{2}):(\d{2})/.exec(v);
  if (m) return `${m[1]}:${m[2]}`;
  return new Date(v).toLocaleTimeString(undefined, { timeStyle: "short" });
};

/** "FRONT_DESK" -> "Front desk" */
export const label = (v: string | null | undefined): string =>
  v ? v.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "—";

export const WEEKDAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

export const weekday = (n: number | null | undefined): string =>
  n == null || n < 0 || n > 6 ? "—" : WEEKDAYS[n];

export const today = (): string => new Date().toISOString().slice(0, 10);

/** Pull a human message out of an ApiError body. */
export function apiMessage(err: unknown): string {
  const e = err as { status?: number; body?: unknown; message?: string };
  const b = e?.body;
  if (typeof b === "string") return b;
  if (b && typeof b === "object") {
    const rec = b as Record<string, unknown>;
    if (typeof rec.detail === "string") return rec.detail;
    const parts: string[] = [];
    for (const [k, v] of Object.entries(rec)) {
      const val = Array.isArray(v) ? v.join(" ") : String(v);
      parts.push(k === "non_field_errors" ? val : `${label(k)}: ${val}`);
    }
    if (parts.length) return parts.join(" · ");
  }
  if (e?.status === 403) return "You don't have access to that.";
  if (e?.status === 404) return "Not found.";
  return e?.message || "Something went wrong.";
}
