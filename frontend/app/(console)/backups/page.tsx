"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CrudPanel } from "@/components/CrudPanel";
import { Modal } from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { fetchMetrics } from "@/lib/metrics";
import { runBackup } from "@/lib/backups";
import { PageHeader, Card, Badge, Button, Spinner } from "@/components/ui";
import { apiMessage, datetime, label } from "@/lib/format";
import type { BackupRun } from "@/lib/backups";

function mb(bytes: number | null | undefined) {
  if (bytes == null) return "—";
  return `${(bytes / 1_048_576).toFixed(1)} MB`;
}

const tone = (s: string) =>
  s === "SUCCESS" ? "green" : s === "FAILED" ? "red" : "amber";

function RunBackupButton() {
  const qc = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [passphrase, setPassphrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function go() {
    setBusy(true);
    setError("");
    try {
      await runBackup(passphrase.trim());
      toast(
        "success",
        "Backup started — it runs in the background. Refresh in a minute for the result.",
      );
      setOpen(false);
      setPassphrase("");
      qc.invalidateQueries({ queryKey: ["list", "backups"] });
      qc.invalidateQueries({ queryKey: ["metrics"] });
    } catch (err) {
      setError(apiMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Run backup now
      </Button>
      <Modal
        open={open}
        onClose={() => !busy && setOpen(false)}
        title="Run a backup now"
      >
        <div className="space-y-4 text-sm">
          <p className="text-[var(--campus-muted)]">
            Runs the same encrypted <code>pg_dump</code> + media backup as the
            scheduled nightly job, straight away. Use it before a risky change —
            a bulk import, a version upgrade, end-of-term archiving — so you have
            a known-good restore point.
          </p>
          <label className="block">
            <span className="mb-1 block font-medium">Backup passphrase</span>
            <input
              type="password"
              autoComplete="off"
              value={passphrase}
              onChange={(e) => setPassphrase(e.target.value)}
              className="w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm focus:border-[var(--campus-accent)] focus:outline-none"
              placeholder="•••••••••••"
            />
            <span className="mt-1 block text-xs text-[var(--campus-muted)]">
              Leave blank if the server already has{" "}
              <code>CAMPUS_BACKUP_PASSPHRASE</code> configured. It is used only
              for this one run and is never stored.
            </span>
          </label>
          {error && <p className="text-xs text-red-600">{error}</p>}
          <div className="flex justify-end gap-2 border-t border-[var(--campus-line)] pt-3">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setOpen(false)}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button size="sm" onClick={go} disabled={busy}>
              {busy ? "Starting…" : "Start backup"}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}

function Health() {
  const q = useQuery({ queryKey: ["metrics"], queryFn: fetchMetrics });
  const b = q.data?.system?.backup;
  if (q.isLoading) return <Spinner />;
  if (!b)
    return (
      <Card className="p-4 text-sm text-[var(--campus-muted)]">
        Backup health is shown to Superadmin and Admin.
      </Card>
    );

  const rows: [string, string, boolean?][] = [
    [
      "Last successful backup",
      b.last_success_at
        ? `${datetime(b.last_success_at)}${
            b.last_success_age_hours != null
              ? ` · ${b.last_success_age_hours} h ago`
              : ""
          }`
        : "never",
      b.stale,
    ],
    ["Last archive size", mb(b.last_success_bytes)],
    ["Archives kept", b.archives_retained != null ? String(b.archives_retained) : "—"],
    ["Runs (7 days)", `${b.runs_7d}${b.failures_7d ? ` · ${b.failures_7d} failed` : ""}`, b.failures_7d > 0],
    [
      "Last restore verified",
      b.last_verified_at ? datetime(b.last_verified_at) : "never — run restore.ps1 -Simulate on a spare machine",
      !b.last_verified_at,
    ],
    ["Most recent run", b.last_status ? label(b.last_status) : "—", b.last_status === "FAILED"],
  ];

  return (
    <Card
      className={`mb-6 ${b.stale ? "border-l-4 border-l-amber-500" : "border-l-4 border-l-emerald-500"}`}
    >
      <div className="flex items-center justify-between border-b border-[var(--campus-line)] px-4 py-3">
        <span className="text-sm font-semibold">Backup health</span>
        <Badge tone={b.stale ? "amber" : "green"}>
          {!b.configured
            ? "not configured"
            : b.stale
              ? "attention needed"
              : "healthy"}
        </Badge>
      </div>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 px-4 py-3 text-sm sm:grid-cols-2">
        {rows.map(([k, v, warn]) => (
          <div key={k} className="flex justify-between gap-4">
            <dt className="text-[var(--campus-muted)]">{k}</dt>
            <dd className={`text-right ${warn ? "font-semibold text-amber-600" : ""}`}>
              {v}
            </dd>
          </div>
        ))}
      </dl>
      {!b.configured && (
        <p className="px-4 pb-3 text-xs text-[var(--campus-muted)]">
          No backup has ever reported in. Schedule{" "}
          <code>C:\ProgramData\Campus\scripts\backup.ps1</code> in Task Scheduler,
          or take one now with <strong>Run backup now</strong> above.
        </p>
      )}
      {b.last_error && (
        <p className="px-4 pb-3 text-xs text-red-600">Last error: {b.last_error}</p>
      )}
    </Card>
  );
}

export default function BackupsPage() {
  return (
    <div>
      <PageHeader
        title="Backups"
        subtitle="Every backup and restore-verification run reported by backup.ps1 / restore.ps1. Backups are normally scheduled on the server; use Run backup now for an on-demand one."
        actions={<RunBackupButton />}
      />
      <Health />
      <CrudPanel<BackupRun>
        resource="backups"
        singular="backup run"
        canCreate={false}
        canEdit={false}
        canDelete={false}
        columns={[
          { header: "Started", cell: (r) => datetime(r.started_at) },
          { header: "Kind", cell: (r) => label(r.kind) },
          {
            header: "Status",
            cell: (r) => <Badge tone={tone(r.status)}>{label(r.status)}</Badge>,
          },
          { header: "Size", cell: (r) => mb(r.size_bytes) },
          {
            header: "Duration",
            cell: (r) => (r.duration_seconds != null ? `${r.duration_seconds}s` : "—"),
          },
          { header: "Host", cell: (r) => r.host || "—" },
        ]}
        detailTitle={(r) => `${label(r.kind)} backup — ${datetime(r.started_at)}`}
        detailFields={[
          { label: "Kind", value: (r) => label(r.kind as string) },
          { label: "Status", value: (r) => label(r.status as string) },
          { label: "Started", value: (r) => datetime(r.started_at as string) },
          {
            label: "Finished",
            value: (r) => (r.finished_at ? datetime(r.finished_at as string) : "—"),
          },
          {
            label: "Duration",
            value: (r) =>
              r.duration_seconds != null ? `${r.duration_seconds} s` : "—",
          },
          { label: "Archive", value: (r) => (r.archive_name as string) || "—" },
          { label: "Size", value: (r) => mb(r.size_bytes as number) },
          { label: "Encrypted", value: (r) => (r.encrypted ? "Yes (AES-256)" : "No") },
          { label: "Database dumped", value: (r) => (r.database_ok ? "Yes" : "No") },
          { label: "Media included", value: (r) => (r.media_ok ? "Yes" : "No") },
          {
            label: "Archives kept",
            value: (r) =>
              r.archives_retained != null ? String(r.archives_retained) : "—",
          },
          { label: "Host", value: (r) => (r.host as string) || "—" },
          { label: "Build", value: (r) => (r.build as string) || "—" },
          {
            label: "Triggered by",
            value: (r) => (r.triggered_by_label as string) || "scheduled task",
          },
          { label: "Error", value: (r) => (r.error as string) || "—", long: true },
        ]}
      />
    </div>
  );
}
