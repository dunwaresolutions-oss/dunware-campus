"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";

type Kind = "success" | "error" | "info";
interface Toast {
  id: number;
  kind: Kind;
  text: string;
}

const Ctx = createContext<(kind: Kind, text: string) => void>(() => {});

export function useToast() {
  return useContext(Ctx);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);

  const push = useCallback((kind: Kind, text: string) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs, { id, kind, text }]);
    setTimeout(() => setItems((xs) => xs.filter((t) => t.id !== id)), 4500);
  }, []);

  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-50 flex w-80 flex-col gap-2.5">
        {items.map((t) => (
          <div
            key={t.id}
            className={`campus-toast pointer-events-auto flex items-start gap-2.5 rounded-xl border border-[var(--glass-border)] border-l-4 px-3.5 py-2.5 text-sm shadow-[var(--campus-shadow-md)] [backdrop-filter:blur(14px)_saturate(160%)] ${
              t.kind === "success"
                ? "border-l-emerald-500 bg-emerald-50/80 text-emerald-900 dark:bg-emerald-950/70 dark:text-emerald-200"
                : t.kind === "error"
                  ? "border-l-red-500 bg-red-50/80 text-red-900 dark:bg-red-950/70 dark:text-red-200"
                  : "border-l-[var(--campus-accent)] bg-white/70 text-neutral-800 dark:bg-neutral-900/70 dark:text-neutral-200"
            }`}
          >
            <span aria-hidden className="mt-px shrink-0 font-semibold">
              {t.kind === "success" ? "✓" : t.kind === "error" ? "!" : "i"}
            </span>
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
