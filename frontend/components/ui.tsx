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
    "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition disabled:opacity-50 disabled:pointer-events-none";
  const sizes = { sm: "px-2.5 py-1 text-xs", md: "px-3.5 py-2 text-sm" };
  const variants = {
    primary: "bg-sky-700 text-white hover:bg-sky-800",
    danger: "bg-red-600 text-white hover:bg-red-700",
    ghost: "border border-neutral-300 bg-white text-neutral-800 hover:bg-neutral-50",
    subtle: "text-sky-700 hover:bg-sky-50",
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
    <div className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold text-neutral-900">{title}</h1>
        {subtitle && (
          <p className="mt-1 max-w-2xl text-sm text-neutral-500">{subtitle}</p>
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
      className={`rounded-lg border border-neutral-200 bg-white ${className}`}
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
    neutral: "bg-neutral-100 text-neutral-700",
    green: "bg-emerald-100 text-emerald-800",
    amber: "bg-amber-100 text-amber-800",
    red: "bg-red-100 text-red-800",
    sky: "bg-sky-100 text-sky-800",
  };
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center gap-2 p-8 text-sm text-neutral-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-neutral-300 border-t-sky-600" />
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
    <div className="flex flex-col items-center gap-3 p-10 text-center text-sm text-neutral-500">
      <p>{message}</p>
      {action}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      {message}
    </div>
  );
}

/* ------------------------------------------------------------------ table */

export interface Column<T> {
  header: string;
  // returns anything React can render; screens often produce `unknown` from
  // the loosely-typed row bag, which Table stringifies safely.
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
          <tr className="border-b border-neutral-200 text-left text-xs uppercase tracking-wide text-neutral-500">
            {columns.map((c) => (
              <th key={c.header} className="px-3 py-2 font-medium">
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
              className={`border-b border-neutral-100 ${
                onRowClick ? "cursor-pointer hover:bg-neutral-50" : ""
              }`}
            >
              {columns.map((c) => (
                <td key={c.header} className={`px-3 py-2.5 ${c.className ?? ""}`}>
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
    <div className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition ${
            active === t.key
              ? "border-sky-600 text-sky-700"
              : "border-transparent text-neutral-500 hover:text-neutral-800"
          }`}
        >
          {t.label}
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
    <div className="flex items-center justify-between px-3 py-2 text-xs text-neutral-500">
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
