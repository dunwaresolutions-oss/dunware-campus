"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useQueryParam } from "@/lib/hooks";
import { getSchool, rotateSchoolToken, type SchoolWithToken } from "@/lib/schools";
import { useToast } from "@/components/Toast";
import { apiMessage, date, label } from "@/lib/format";
import { Badge, Button, Card, ErrorNote, PageHeader, Spinner } from "@/components/ui";

type Tone = "neutral" | "green" | "amber" | "red" | "sky" | "violet";

const STATUS_TONE: Record<string, Tone> = {
  NEVER_SYNCED: "neutral",
  OK: "green",
  ERROR: "red",
};

export default function SchoolDetailPage() {
  const id = useQueryParam("id");
  const toast = useToast();
  const qc = useQueryClient();
  const [rotated, setRotated] = useState<SchoolWithToken | null>(null);
  const [busy, setBusy] = useState(false);

  const school = useQuery({
    queryKey: ["school", id],
    queryFn: () => getSchool(id as string),
    enabled: !!id,
  });

  async function onRotate() {
    if (!id) return;
    if (!window.confirm("Rotate this school's sync token? Its old token stops working immediately.")) {
      return;
    }
    setBusy(true);
    try {
      const result = await rotateSchoolToken(id);
      setRotated(result);
      qc.invalidateQueries({ queryKey: ["school", id] });
      toast("success", "Token rotated");
    } catch (err) {
      toast("error", apiMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (!id) return null;
  if (school.isLoading) return <Spinner />;
  if (school.isError) return <ErrorNote message={apiMessage(school.error)} />;
  if (!school.data) return null;
  const s = school.data;

  return (
    <div className="space-y-6">
      <PageHeader title={s.name} subtitle={s.district || undefined} />

      <Card className="p-5">
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--campus-muted)]">School ID</dt>
            <dd className="mt-0.5 font-mono text-sm break-all">{s.id}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--campus-muted)]">Sync status</dt>
            <dd className="mt-0.5">
              <Badge tone={STATUS_TONE[s.sync_status]}>{label(s.sync_status)}</Badge>
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--campus-muted)]">Last synced</dt>
            <dd className="mt-0.5 text-sm">{date(s.last_synced_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--campus-muted)]">Snapshot schema version</dt>
            <dd className="mt-0.5 text-sm">{s.snapshot_schema_version ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--campus-muted)]">Contact email</dt>
            <dd className="mt-0.5 text-sm">{s.contact_email || "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--campus-muted)]">Active</dt>
            <dd className="mt-0.5 text-sm">{s.active ? "Yes" : "No"}</dd>
          </div>
        </dl>
      </Card>

      <Card className="p-5">
        <h2 className="text-sm font-semibold">Sync token</h2>
        <p className="mt-1 text-sm text-[var(--campus-muted)]">
          Rotating issues a brand new token and invalidates the old one immediately.
          The school&apos;s own install needs the new one pasted into its own
          link setup before its next sync.
        </p>
        <Button variant="danger" className="mt-3" onClick={onRotate} disabled={busy}>
          {busy ? "Rotating…" : "Rotate token"}
        </Button>
        {rotated && (
          <div className="mt-3 rounded-lg border-l-4 border-l-emerald-500 bg-emerald-50/60 p-3 text-sm dark:bg-emerald-950/40">
            <p className="font-medium">New token (shown once):</p>
            <p className="mt-1 break-all font-mono">{rotated.sync_token}</p>
          </div>
        )}
      </Card>
    </div>
  );
}
