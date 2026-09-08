"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { list, listAll, type Query } from "./resource";

/** Read one URL query param, client-side only — no <Suspense> needed, which
 *  keeps `output: export` happy. Updates on back/forward. */
export function useQueryParam(name: string): string | null {
  const [value, setValue] = useState<string | null>(null);
  useEffect(() => {
    const read = () =>
      setValue(new URLSearchParams(window.location.search).get(name));
    read();
    window.addEventListener("popstate", read);
    return () => window.removeEventListener("popstate", read);
  }, [name]);
  return value;
}

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
