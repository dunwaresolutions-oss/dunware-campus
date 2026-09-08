"use client";

import { useState } from "react";
import { useList, useQueryParam } from "@/lib/hooks";
import type { AuditRow } from "@/lib/audit";
import { PageHeader, Card, Spinner, Badge, Paginator, ErrorNote } from "@/components/ui";
import { datetime, apiMessage } from "@/lib/format";

const CHIPS: { key: string; label: string }[] = [
  { key: "", label: "All" },
  { key: "security", label: "Security" },
  { key: "auth", label: "Sign-in" },
  { key: "changes", label: "Changes" },
  { key: "reads", label: "Record views" },
  { key: "governance", label: "Export / erase" },
];

const tone = (a: string) => {
  if (["LOGIN_FAILED", "LOCKOUT", "PERMISSION_DENIED"].includes(a)) return "red";
  if (["EXPORT", "ERASE", "DELETE"].includes(a)) return "amber";
  if (["CREATE", "UPDATE"].includes(a)) return "sky";
  if (["LOGIN", "LOGOUT", "MFA_ENROLLED", "MFA_VERIFIED"].includes(a)) return "green";
  return "neutral";
};

export default function AuditPage() {
  const paramSet = useQueryParam("set");
  const paramAction = useQueryParam("action");
  const [preset, setPreset] = useState(paramSet ?? "");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  const query: Record<string, string | number> = { page };
  if (preset) query.set = preset;
  if (paramAction && !preset) query.action = paramAction;
  if (q.trim()) query.q = q.trim();

  const rows = useList<AuditRow>("audit", query);

  return (
    <div>
      <PageHeader
        title="Audit log"
        subtitle="Every create, update, delete — and every read of a sensitive record. Append-only; entries can never be edited or deleted from the app."
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {CHIPS.map((c) => (
          <button
            key={c.key || "all"}
            onClick={() => {
              setPreset(c.key);
              setPage(1);
            }}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              preset === c.key
                ? "bg-[var(--campus-accent)] text-white"
                : "border border-[var(--campus-line)] text-[var(--campus-muted)] hover:border-[var(--campus-accent)]"
            }`}
          >
            {c.label}
          </button>
        ))}
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          placeholder="Filter by summary, person, or record type…"
          className="ml-auto w-64 rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-1.5 text-sm text-[var(--campus-fg)] focus:border-[var(--campus-accent)] focus:outline-none"
        />
      </div>

      <Card>
        {rows.isLoading ? (
          <Spinner />
        ) : rows.isError ? (
          <div className="p-4">
            <ErrorNote message={apiMessage(rows.error)} />
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--campus-line)] text-left text-xs uppercase tracking-wide text-[var(--campus-muted)]">
                    <th className="px-3 py-2.5 font-medium">When</th>
                    <th className="px-3 py-2.5 font-medium">Who</th>
                    <th className="px-3 py-2.5 font-medium">Action</th>
                    <th className="px-3 py-2.5 font-medium">Record</th>
                    <th className="px-3 py-2.5 font-medium">Summary</th>
                    <th className="px-3 py-2.5 font-medium">IP</th>
                  </tr>
                </thead>
                <tbody>
                  {(rows.data?.results ?? []).length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-3 py-6 text-center text-[var(--campus-muted)]">
                        No entries match.
                      </td>
                    </tr>
                  )}
                  {(rows.data?.results ?? []).map((e) => (
                    <tr key={e.id} className="border-b border-[var(--campus-line)] last:border-0">
                      <td className="whitespace-nowrap px-3 py-2.5 text-[var(--campus-muted)]">
                        {datetime(e.at)}
                      </td>
                      <td className="px-3 py-2.5">
                        {e.actor_label || "system"}
                        {e.actor_role && (
                          <span className="text-xs text-[var(--campus-muted)]">
                            {" "}
                            · {e.actor_role.replace(/_/g, " ").toLowerCase()}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2.5">
                        <Badge tone={tone(e.action)}>
                          {e.action.replace(/_/g, " ")}
                        </Badge>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2.5 text-[var(--campus-muted)]">
                        {e.object_type
                          ? `${e.object_type}${e.object_id ? ` #${e.object_id.slice(0, 8)}` : ""}`
                          : "—"}
                      </td>
                      <td className="px-3 py-2.5">{e.summary || "—"}</td>
                      <td className="whitespace-nowrap px-3 py-2.5 text-[var(--campus-muted)]">
                        {e.source_ip || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Paginator page={page} count={rows.data?.count ?? 0} onPage={setPage} />
          </>
        )}
      </Card>
    </div>
  );
}
