"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { search, type SearchGroup } from "@/lib/search";

/** Console-wide search. Open with the sidebar button or Ctrl/Cmd+K. */
export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [groups, setGroups] = useState<SearchGroup[]>([]);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const flat = groups.flatMap((g) => g.items);

  const close = useCallback(() => {
    setOpen(false);
    setQ("");
    setGroups([]);
    setActive(0);
  }, []);

  // Ctrl/Cmd+K toggles; "/" opens when not already typing somewhere
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && k === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (
        k === "/" &&
        !open &&
        !/^(input|textarea|select)$/i.test(
          (e.target as HTMLElement)?.tagName ?? "",
        )
      ) {
        e.preventDefault();
        setOpen(true);
      }
    };
    const openIt = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("campus:search", openIt);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("campus:search", openIt);
    };
  }, [open]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 20);
  }, [open]);

  // debounced search
  useEffect(() => {
    if (!open) return;
    const term = q.trim();
    if (term.length < 2) {
      setGroups([]);
      setBusy(false);
      return;
    }
    setBusy(true);
    const id = setTimeout(async () => {
      try {
        const r = await search(term);
        setGroups(r.groups);
        setActive(0);
      } catch {
        setGroups([]);
      } finally {
        setBusy(false);
      }
    }, 220);
    return () => clearTimeout(id);
  }, [q, open]);

  function go(route: string) {
    close();
    router.push(route);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") return close();
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, flat.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && flat[active]) {
      e.preventDefault();
      go(flat[active].route);
    }
  }

  if (!open) return null;

  let idx = -1;
  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center px-4 pt-[12vh]"
      onMouseDown={close}
    >
      <div className="absolute inset-0 bg-black/30 [backdrop-filter:blur(2px)]" />
      <div
        className="glass campus-modal-panel relative w-full max-w-xl overflow-hidden rounded-2xl shadow-[var(--campus-shadow-lg)]"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Search students, guardians, staff, groups, report cards…"
          className="w-full border-b border-[var(--campus-line)] bg-transparent px-4 py-3.5 text-sm text-[var(--campus-fg)] placeholder:text-[var(--campus-muted)] focus:outline-none"
        />
        <div className="max-h-[52vh] overflow-y-auto">
          {q.trim().length < 2 ? (
            <p className="px-4 py-6 text-center text-xs text-[var(--campus-muted)]">
              Type at least two characters. <kbd>↑</kbd><kbd>↓</kbd> to move,
              <kbd>↵</kbd> to open, <kbd>Esc</kbd> to close.
            </p>
          ) : busy && groups.length === 0 ? (
            <p className="px-4 py-6 text-center text-xs text-[var(--campus-muted)]">
              Searching…
            </p>
          ) : groups.length === 0 ? (
            <p className="px-4 py-6 text-center text-xs text-[var(--campus-muted)]">
              Nothing matches “{q.trim()}”.
            </p>
          ) : (
            groups.map((g) => (
              <div key={g.title} className="py-1.5">
                <div className="px-4 pb-1 pt-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
                  {g.title}
                </div>
                {g.items.map((it) => {
                  idx += 1;
                  const on = idx === active;
                  return (
                    <button
                      key={it.id + it.route}
                      onMouseEnter={() => setActive(flat.indexOf(it))}
                      onClick={() => go(it.route)}
                      className={`flex w-full flex-col items-start px-4 py-2 text-left transition-colors ${
                        on
                          ? "bg-[var(--campus-accent-soft)] text-[var(--campus-accent)]"
                          : "hover:bg-black/[0.03] dark:hover:bg-white/[0.04]"
                      }`}
                    >
                      <span className="text-sm font-medium">{it.label}</span>
                      {it.sublabel && (
                        <span className="text-xs text-[var(--campus-muted)]">
                          {it.sublabel}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
