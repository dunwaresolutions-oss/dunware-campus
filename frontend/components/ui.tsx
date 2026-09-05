"use client";

import Link from "next/link";
import type { ReactNode } from "react";

/* ---------------------------------------------------------------- button */

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger" | "subtle";
  size?: "sm" | "md";
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  ...rest
}: BtnProps) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium " +
    "transition-all duration-150 ease-out select-none " +
    "active:scale-[0.97] disabled:opacity-50 disabled:pointer-events-none " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--campus-ring)] focus-visible:ring-offset-1";
  const sizes = { sm: "px-2.5 py-1 text-xs", md: "px-3.5 py-2 text-sm" };
  const variants = {
    primary:
      "bg-[var(--campus-accent)] text-white shadow-sm hover:bg-[var(--campus-accent-strong)] hover:shadow-md hover:-translate-y-px",
    danger:
      "bg-red-600 text-white shadow-sm hover:bg-red-700 hover:shadow-md hover:-translate-y-px",
    ghost:
      "border border-[var(--campus-line)] bg-[var(--campus-panel)] text-[var(--campus-fg)] hover:border-[var(--campus-accent)] hover:text-[var(--campus-accent)] hover:shadow-sm",
    subtle:
      "text-[var(--campus-accent)] hover:bg-[var(--campus-accent-soft)]",
  };
  return (
    <button
      className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}
      {...rest}
    />
  );
}

/* ------------------------------------------------------------ page header */

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="campus-enter mb-7 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--campus-fg)]">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-[var(--campus-muted)]">
            {subtitle}
          </p>
        )}
      </div>
      {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
    </div>
  );
}

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl border border-[var(--campus-line)] bg-[var(--campus-panel)] shadow-[var(--campus-shadow-sm)] ${className}`}
    >
      {children}
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "green" | "amber" | "red" | "sky";
}) {
  const tones = {
    neutral: "bg-neutral-100 text-neutral-700 ring-neutral-200 dark:bg-neutral-800 dark:text-neutral-300 dark:ring-neutral-700",
    green: "bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:ring-emerald-800",
    amber: "bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:ring-amber-800",
    red: "bg-red-50 text-red-700 ring-red-200 dark:bg-red-950 dark:text-red-300 dark:ring-red-800",
    sky: "bg-sky-50 text-sky-700 ring-sky-200 dark:bg-sky-950 dark:text-sky-300 dark:ring-sky-800",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center gap-2.5 p-8 text-sm text-[var(--campus-muted)]">
      <span
        className="h-4 w-4 rounded-full border-2 border-[var(--campus-line)] border-t-[var(--campus-accent)]"
        style={{ animation: "campus-spin 0.7s linear infinite" }}
      />
      Loading…
    </div>
  );
}

export function EmptyState({
  message,
  action,
}: {
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="campus-enter flex flex-col items-center gap-3 p-12 text-center text-sm text-[var(--campus-muted)]">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--campus-accent-soft)] text-[var(--campus-accent)]">
        ○
      </div>
      <p>{message}</p>
      {action}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="campus-enter rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
      {message}
    </div>
  );
}

/* ------------------------------------------------------------------ table */

export interface Column<T> {
  header: string;
  cell: (row: T) => unknown;
  className?: string;
}

function renderCell(v: unknown): ReactNode {
  if (v == null || typeof v === "boolean") return v as ReactNode;
  if (
    typeof v === "string" ||
    typeof v === "number" ||
    (typeof v === "object" && "$$typeof" in (v as object))
  )
    return v as ReactNode;
  return String(v);
}

export function Table<T extends { id: string | number }>({
  columns,
  rows,
  onRowClick,
  empty = "Nothing here yet.",
}: {
  columns: Column<T>[];
  rows: T[];
  onRowClick?: (row: T) => void;
  empty?: string;
}) {
  if (rows.length === 0) return <EmptyState message={empty} />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--campus-line)] text-left text-xs uppercase tracking-wide text-[var(--campus-muted)]">
            {columns.map((c) => (
              <th key={c.header} className="px-3 py-2.5 font-medium">
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={`border-b border-[var(--campus-line)]/60 transition-colors duration-100 ${
                onRowClick
                  ? "cursor-pointer hover:bg-[var(--campus-accent-soft)]/60"
                  : "hover:bg-black/[0.015] dark:hover:bg-white/[0.02]"
              }`}
            >
              {columns.map((c) => (
                <td key={c.header} className={`px-3 py-3 ${c.className ?? ""}`}>
                  {renderCell(c.cell(row))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------- tabs */

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: string; label: string }[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="mb-6 flex flex-wrap gap-1 border-b border-[var(--campus-line)]">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={`relative -mb-px px-3 py-2 text-sm font-medium transition-colors duration-150 ${
            active === t.key
              ? "text-[var(--campus-accent)]"
              : "text-[var(--campus-muted)] hover:text-[var(--campus-fg)]"
          }`}
        >
          {t.label}
          <span
            className={`absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-[var(--campus-accent)] transition-all duration-200 ${
              active === t.key ? "opacity-100" : "opacity-0"
            }`}
          />
        </button>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------- paginator */

export function Paginator({
  page,
  count,
  pageSize = 25,
  onPage,
}: {
  page: number;
  count: number;
  pageSize?: number;
  onPage: (p: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-between border-t border-[var(--campus-line)] px-3 py-2.5 text-xs text-[var(--campus-muted)]">
      <span>
        {count} total · page {page} of {pages}
      </span>
      <div className="flex gap-1">
        <Button
          size="sm"
          variant="ghost"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          Prev
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}

export { Link };
