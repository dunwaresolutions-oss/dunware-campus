"use client";

import { useQuery } from "@tanstack/react-query";
import { list, listAll, type Query } from "./resource";

/** Paged list for a table. */
export function useList<T>(resource: string, query?: Query, enabled = true) {
  return useQuery({
    queryKey: ["list", resource, query ?? {}],
    queryFn: () => list<T>(resource, query),
    enabled,
  });
}

/** Every row of a resource — for FK <select> options. Cached longer. */
export function useAll<T>(resource: string, query?: Query, enabled = true) {
  return useQuery({
    queryKey: ["all", resource, query ?? {}],
    queryFn: () => listAll<T>(resource, query),
    staleTime: 120_000,
    enabled,
  });
}

/** Turn a list of rows into <select> options via a label picker. */
export function options<T extends { id: string | number }>(
  rows: T[] | undefined,
  toLabel: (row: T) => string,
) {
  return (rows ?? []).map((r) => ({ value: r.id, label: toLabel(r) }));
}
