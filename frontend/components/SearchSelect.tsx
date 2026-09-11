"use client";

import { useEffect, useRef, useState } from "react";

export interface SearchOption {
  value: string;
  label: string;
  sublabel?: string;
}

/**
 * A type-to-search combobox for picking one record out of a list too long
 * for a plain <select> (e.g. 1,200 students) — debounced live results from
 * `search(term)`, click or arrow keys + Enter to pick.
 */
export function SearchSelect({
  value,
  initialLabel,
  onChange,
  search,
  placeholder = "Type to search…",
  disabled,
  error,
}: {
  value: string;
  /** How to show `value` before the user has typed anything (e.g. when editing). */
  initialLabel?: string;
  onChange: (value: string, label: string) => void;
  search: (term: string) => Promise<SearchOption[]>;
  placeholder?: string;
  disabled?: boolean;
  error?: string;
}) {
  const [term, setTerm] = useState("");
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<SearchOption[]>([]);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState(0);
  const [label, setLabel] = useState(initialLabel ?? "");
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    if (!open) return;
    const q = term.trim();
    if (q.length < 1) {
      setOptions([]);
      return;
    }
    setBusy(true);
    const id = setTimeout(async () => {
      try {
        const results = await search(q);
        setOptions(results);
        setActive(0);
      } catch {
        setOptions([]);
      } finally {
        setBusy(false);
      }
    }, 200);
    return () => clearTimeout(id);
  }, [term, open, search]);

  function pick(o: SearchOption) {
    onChange(o.value, o.label);
    setLabel(o.label);
    setOpen(false);
    setTerm("");
  }

  function clear() {
    onChange("", "");
    setLabel("");
    setTerm("");
  }

  const box =
    `w-full rounded-lg border bg-[var(--campus-input-bg)] text-[var(--campus-fg)] px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--campus-ring)] ${
      error ? "border-red-400 focus:border-red-400" : "border-[var(--campus-line)] focus:border-[var(--campus-accent)]"
    }`;

  return (
    <div ref={boxRef} className="relative">
      <input
        className={box}
        value={open ? term : label}
        placeholder={value && !open ? undefined : placeholder}
        disabled={disabled}
        onFocus={() => {
          setOpen(true);
          setTerm("");
        }}
        onChange={(e) => setTerm(e.target.value)}
        onKeyDown={(e) => {
          if (!open) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((i) => Math.min(i + 1, options.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((i) => Math.max(i - 1, 0));
          } else if (e.key === "Enter" && options[active]) {
            e.preventDefault();
            pick(options[active]);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      {value && !open && !disabled && (
        <button
          type="button"
          onClick={clear}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--campus-muted)] hover:text-[var(--campus-fg)]"
          aria-label="Clear"
        >
          ✕
        </button>
      )}
      {open && (
        <div className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] py-1 shadow-[var(--campus-shadow-md)]">
          {busy ? (
            <div className="px-3 py-2 text-xs text-[var(--campus-muted)]">Searching…</div>
          ) : term.trim().length < 1 ? (
            <div className="px-3 py-2 text-xs text-[var(--campus-muted)]">
              Type at least one character…
            </div>
          ) : options.length === 0 ? (
            <div className="px-3 py-2 text-xs text-[var(--campus-muted)]">
              No matches for “{term.trim()}”.
            </div>
          ) : (
            options.map((o, i) => (
              <button
                key={o.value}
                type="button"
                onMouseEnter={() => setActive(i)}
                onClick={() => pick(o)}
                className={`flex w-full flex-col items-start px-3 py-1.5 text-left text-sm ${
                  i === active
                    ? "bg-[var(--campus-accent-soft)] text-[var(--campus-accent)]"
                    : "hover:bg-black/[0.03] dark:hover:bg-white/[0.04]"
                }`}
              >
                <span>{o.label}</span>
                {o.sublabel && (
                  <span className="text-xs text-[var(--campus-muted)]">{o.sublabel}</span>
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
