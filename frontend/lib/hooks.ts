"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { list, listAll, type Query } from "./resource";

// Next's router.push()/replace() call history.pushState/replaceState, which
// (unlike a user's back/forward) never fires "popstate" — so a component
// already mounted on the same route (e.g. the command palette jumping from
// one search result straight to another) never saw the new query string.
// Patch the two History methods once to also fire a same-tab event.
let _historyPatched = false;
function ensureHistoryPatched() {
  if (_historyPatched || typeof window === "undefined") return;
  _historyPatched = true;
  const notify = () => window.dispatchEvent(new Event("campus:locationchange"));
  for (const method of ["pushState", "replaceState"] as const) {
    const original = window.history[method];
    window.history[method] = function (...args: Parameters<History[typeof method]>) {
      const ret = original.apply(this, args);
      notify();
      return ret;
    };
  }
  window.addEventListener("popstate", notify);
}

/** Read one URL query param, client-side only — no <Suspense> needed, which
 *  keeps `output: export` happy. Updates on back/forward AND on any
 *  router.push/replace, even to the same route with different params. */
export function useQueryParam(name: string): string | null {
  const [value, setValue] = useState<string | null>(null);
  useEffect(() => {
    ensureHistoryPatched();
    const read = () =>
      setValue(new URLSearchParams(window.location.search).get(name));
    read();
    window.addEventListener("campus:locationchange", read);
    return () => window.removeEventListener("campus:locationchange", read);
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
