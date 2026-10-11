/** Small display helpers -- trimmed from Campus's own lib/format.ts: no
 * money()/currency (Central has no billing concept of its own). */

export const date = (v: string | null | undefined): string =>
  v ? new Date(v).toLocaleDateString(undefined, { dateStyle: "medium" }) : "—";

export const datetime = (v: string | null | undefined): string =>
  v
    ? new Date(v).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";

/** "MINISTRY_ADMIN" -> "Ministry admin" */
export const label = (v: string | null | undefined): string =>
  v ? v.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "—";

export const pct = (v: number | null | undefined): string =>
  v == null ? "—" : `${v}%`;

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
