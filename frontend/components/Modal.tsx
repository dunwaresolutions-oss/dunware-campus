"use client";

import { useEffect, type ReactNode } from "react";
import { Button } from "./ui";

export function Modal({
  open,
  onClose,
  title,
  children,
  wide = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="campus-modal-backdrop fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/40 p-4 backdrop-blur-[2px] sm:p-10"
      onMouseDown={onClose}
    >
      <div
        className={`campus-modal-panel w-full rounded-2xl border border-[var(--campus-line)] bg-[var(--campus-panel)] shadow-[var(--campus-shadow-lg)] ${
          wide ? "max-w-3xl" : "max-w-lg"
        }`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[var(--campus-line)] px-5 py-3.5">
          <h2 className="text-sm font-semibold text-[var(--campus-fg)]">
            {title}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-[var(--campus-muted)] transition-colors hover:bg-black/5 hover:text-[var(--campus-fg)] dark:hover:bg-white/10"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}

export function ConfirmButton({
  onConfirm,
  children,
  message = "Are you sure?",
  variant = "danger",
  size = "sm",
}: {
  onConfirm: () => void;
  children: ReactNode;
  message?: string;
  variant?: "danger" | "ghost";
  size?: "sm" | "md";
}) {
  return (
    <Button
      variant={variant}
      size={size}
      onClick={() => {
        if (window.confirm(message)) onConfirm();
      }}
    >
      {children}
    </Button>
  );
}
