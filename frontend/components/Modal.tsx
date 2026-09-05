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
      className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/30 p-4 sm:p-10"
      onMouseDown={onClose}
    >
      <div
        className={`w-full rounded-lg bg-white shadow-xl ${
          wide ? "max-w-3xl" : "max-w-lg"
        }`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-neutral-200 px-5 py-3">
          <h2 className="text-sm font-semibold text-neutral-900">{title}</h2>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-700"
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
