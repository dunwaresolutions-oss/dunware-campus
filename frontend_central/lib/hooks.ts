"use client";

import { useEffect, useState } from "react";

// Copied from Campus's own lib/hooks.ts: Next's router.push()/replace() call
// history.pushState/replaceState, which (unlike a user's back/forward)
// never fires "popstate" -- patch the two History methods once to also
// fire a same-tab event so a component already mounted on the same route
// sees a changed query string.
let _historyPatched = false;
function ensureHistoryPatched() {
  if (_historyPatched || typeof window === "undefined") return;
  _historyPatched = true;
  const notify = () => window.dispatchEvent(new Event("central:locationchange"));
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

/** Read one URL query param, client-side only -- no <Suspense> needed,
 * which keeps `output: export` happy (a dynamic [id] route segment would
 * need generateStaticParams() to know every id at build time, which is
 * impossible for a school registered after deployment; Campus's own
 * frontend avoids dynamic segments the same way, e.g. people/student/?id=). */
export function useQueryParam(name: string): string | null {
  const [value, setValue] = useState<string | null>(null);
  useEffect(() => {
    ensureHistoryPatched();
    const read = () => setValue(new URLSearchParams(window.location.search).get(name));
    read();
    window.addEventListener("central:locationchange", read);
    return () => window.removeEventListener("central:locationchange", read);
  }, [name]);
  return value;
}
