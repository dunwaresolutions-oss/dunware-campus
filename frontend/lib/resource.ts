/**
 * Generic REST helpers over `api()` for the DRF router resources.
 *
 * DRF PageNumberPagination wraps list responses as
 * `{ count, next, previous, results }`; `list()` unwraps that but also
 * tolerates a bare array (custom list endpoints).
 */
import { api } from "./api";

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export type Query = Record<string, string | number | boolean | undefined | null>;

function qs(query?: Query): string {
  if (!query) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export async function list<T>(resource: string, query?: Query): Promise<Page<T>> {
  const data = await api<Page<T> | T[]>(`/${resource}/${qs(query)}`);
  if (Array.isArray(data)) {
    return { count: data.length, next: null, previous: null, results: data };
  }
  return data;
}

/** Load every page (small on-site datasets — fine to pull in full for dropdowns). */
export async function listAll<T>(resource: string, query?: Query): Promise<T[]> {
  const out: T[] = [];
  let page = 1;
  for (;;) {
    const p = await list<T>(resource, { ...query, page });
    out.push(...p.results);
    if (!p.next) break;
    page += 1;
    if (page > 200) break; // hard stop
  }
  return out;
}

export const retrieve = <T>(resource: string, id: string | number) =>
  api<T>(`/${resource}/${id}/`);

export const create = <T>(resource: string, body: unknown) =>
  api<T>(`/${resource}/`, {
    method: "POST",
    body: body instanceof FormData ? body : JSON.stringify(body),
  });

export const update = <T>(resource: string, id: string | number, body: unknown) =>
  api<T>(`/${resource}/${id}/`, { method: "PUT", body: JSON.stringify(body) });

export const patch = <T>(resource: string, id: string | number, body: unknown) =>
  api<T>(`/${resource}/${id}/`, { method: "PATCH", body: JSON.stringify(body) });

export const remove = (resource: string, id: string | number) =>
  api<void>(`/${resource}/${id}/`, { method: "DELETE" });

/** A DRF @action on a detail route, e.g. act("invoices", id, "issue"). */
export const act = <T>(
  resource: string,
  id: string | number,
  verb: string,
  body?: unknown,
) =>
  api<T>(`/${resource}/${id}/${verb}/`, {
    method: "POST",
    body: JSON.stringify(body ?? {}),
  });

/** A DRF @action on the list route, e.g. actList("offerings/5", "generate_slots"). */
export const actList = <T>(resource: string, verb: string, body?: unknown) =>
  api<T>(`/${resource}/${verb}/`, {
    method: "POST",
    body: JSON.stringify(body ?? {}),
  });
