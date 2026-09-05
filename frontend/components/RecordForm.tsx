"use client";

import { useState } from "react";
import { Button, ErrorNote } from "./ui";
import { apiMessage } from "@/lib/format";

export type FieldType =
  | "text"
  | "textarea"
  | "number"
  | "money"
  | "date"
  | "time"
  | "datetime"
  | "select"
  | "checkbox"
  | "file";

export interface FieldDef {
  name: string;
  label: string;
  type?: FieldType;
  required?: boolean;
  help?: string;
  options?: { value: string | number; label: string }[];
  placeholder?: string;
}

type Values = Record<string, unknown>;

function coerce(field: FieldDef, raw: string | boolean): unknown {
  if (field.type === "checkbox") return Boolean(raw);
  if (raw === "" || raw == null) return field.required ? "" : null;
  if (field.type === "number") return Number(raw);
  if (field.type === "money") return Math.round(Number(raw) * 100);
  return raw;
}

function initial(field: FieldDef, v: Values): string | boolean {
  const cur = v[field.name];
  if (field.type === "checkbox") return Boolean(cur);
  if (cur == null) return "";
  if (field.type === "money" && typeof cur === "number") return String(cur / 100);
  return String(cur);
}

export function RecordForm({
  fields,
  initialValues = {},
  submitLabel = "Save",
  onSubmit,
  onCancel,
}: {
  fields: FieldDef[];
  initialValues?: Values;
  submitLabel?: string;
  onSubmit: (values: Values) => Promise<void>;
  onCancel: () => void;
}) {
  const [state, setState] = useState<Record<string, string | boolean>>(() => {
    const s: Record<string, string | boolean> = {};
    for (const f of fields) s[f.name] = initial(f, initialValues);
    return s;
  });
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError(null);
    setFieldErrors({});
    const out: Values = {};
    for (const f of fields) {
      out[f.name] =
        f.type === "file" ? (files[f.name] ?? null) : coerce(f, state[f.name]);
    }
    try {
      await onSubmit(out);
    } catch (err) {
      const body = (err as { body?: unknown })?.body;
      if (body && typeof body === "object" && !Array.isArray(body)) {
        const fe: Record<string, string> = {};
        for (const [k, v] of Object.entries(body as Record<string, unknown>)) {
          if (k === "detail" || k === "non_field_errors") continue;
          fe[k] = Array.isArray(v) ? v.join(" ") : String(v);
        }
        setFieldErrors(fe);
      }
      setFormError(apiMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const inputCls =
    "w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] text-[var(--campus-fg)] px-3 py-2 text-sm transition-colors focus:border-[var(--campus-accent)] focus:outline-none focus:ring-2 focus:ring-[var(--campus-ring)]";

  return (
    <form onSubmit={submit} className="space-y-4">
      {formError && <ErrorNote message={formError} />}
      {fields.map((f) => {
        const val = state[f.name];
        const err = fieldErrors[f.name];
        return (
          <div key={f.name}>
            <label className="mb-1 block text-xs font-medium text-[var(--campus-muted)]">
              {f.label}
              {f.required && <span className="text-red-500"> *</span>}
            </label>
            {f.type === "textarea" ? (
              <textarea
                className={inputCls}
                rows={3}
                value={val as string}
                placeholder={f.placeholder}
                onChange={(e) =>
                  setState((s) => ({ ...s, [f.name]: e.target.value }))
                }
              />
            ) : f.type === "select" ? (
              <select
                className={inputCls}
                value={val as string}
                onChange={(e) =>
                  setState((s) => ({ ...s, [f.name]: e.target.value }))
                }
              >
                <option value="">—</option>
                {f.options?.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            ) : f.type === "checkbox" ? (
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-[var(--campus-line)]"
                checked={val as boolean}
                onChange={(e) =>
                  setState((s) => ({ ...s, [f.name]: e.target.checked }))
                }
              />
            ) : f.type === "file" ? (
              <input
                type="file"
                className="block w-full text-sm text-[var(--campus-muted)] file:mr-3 file:rounded-md file:border file:border-[var(--campus-line)] file:bg-[var(--campus-input-bg)] file:px-3 file:py-1.5 file:text-sm file:text-[var(--campus-fg)] hover:file:border-[var(--campus-accent)]"
                onChange={(e) =>
                  setFiles((s) => ({
                    ...s,
                    [f.name]: e.target.files?.[0] ?? null,
                  }))
                }
              />
            ) : (
              <input
                className={inputCls}
                type={
                  f.type === "number" || f.type === "money"
                    ? "number"
                    : f.type === "date"
                      ? "date"
                      : f.type === "time"
                        ? "time"
                        : f.type === "datetime"
                          ? "datetime-local"
                          : "text"
                }
                step={f.type === "money" ? "0.01" : undefined}
                value={val as string}
                placeholder={f.placeholder}
                onChange={(e) =>
                  setState((s) => ({ ...s, [f.name]: e.target.value }))
                }
              />
            )}
            {f.help && !err && (
              <p className="mt-1 text-xs text-[var(--campus-muted)]">{f.help}</p>
            )}
            {err && <p className="mt-1 text-xs text-red-600">{err}</p>}
          </div>
        );
      })}
      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}
