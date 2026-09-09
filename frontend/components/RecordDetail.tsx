"use client";

import { Fragment, type ReactNode } from "react";

export interface DetailField {
  label: string;
  /** Return the display value for this row. "" / null / undefined render as "—". */
  value: (row: Record<string, unknown>) => ReactNode;
  /** Render as a full-width pre-wrapped block instead of a definition-list row. */
  long?: boolean;
}

function isEmpty(v: ReactNode): boolean {
  return v === "" || v == null || v === false;
}

/**
 * A read-only rendering of one record: short fields as a two-column
 * definition list, `long` fields as pre-wrapped blocks underneath. Used by
 * CrudPanel's built-in "Open" view so every list has a consistent preview.
 */
export function RecordDetail({
  fields,
  row,
}: {
  fields: DetailField[];
  row: Record<string, unknown>;
}) {
  const short = fields.filter((f) => !f.long);
  const long = fields.filter((f) => f.long);

  return (
    <div className="space-y-5">
      {short.length > 0 && (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-sm">
          {short.map((f) => {
            const v = f.value(row);
            return (
              <Fragment key={f.label}>
                <dt className="text-[var(--campus-muted)]">{f.label}</dt>
                <dd className="min-w-0 break-words">{isEmpty(v) ? "—" : v}</dd>
              </Fragment>
            );
          })}
        </dl>
      )}
      {long.map((f) => {
        const v = f.value(row);
        return (
          <div key={f.label}>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
              {f.label}
            </div>
            <div className="whitespace-pre-wrap rounded-md border border-[var(--campus-line)] bg-black/[0.02] p-3 text-sm dark:bg-white/[0.03]">
              {isEmpty(v) ? "—" : v}
            </div>
          </div>
        );
      })}
    </div>
  );
}
