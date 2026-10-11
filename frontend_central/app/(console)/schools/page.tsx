"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listSchools, registerSchool, type SchoolWithToken } from "@/lib/schools";
import { useToast } from "@/components/Toast";
import { apiMessage, date, label } from "@/lib/format";
import {
  Badge,
  Button,
  Card,
  ErrorNote,
  Link,
  PageHeader,
  Spinner,
  Table,
} from "@/components/ui";

type Tone = "neutral" | "green" | "amber" | "red" | "sky" | "violet";

const STATUS_TONE: Record<string, Tone> = {
  NEVER_SYNCED: "neutral",
  OK: "green",
  ERROR: "red",
};

function RegisterForm({ onDone }: { onDone: (s: SchoolWithToken) => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [district, setDistrict] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const school = await registerSchool({
        name: name.trim(),
        district: district.trim(),
        contact_email: contactEmail.trim(),
      });
      qc.invalidateQueries({ queryKey: ["schools"] });
      toast("success", `${school.name} registered`);
      setName("");
      setDistrict("");
      setContactEmail("");
      onDone(school);
    } catch (err) {
      setError(apiMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const field =
    "w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm";

  return (
    <Card className="p-5">
      <h2 className="mb-3 text-sm font-semibold">Register a school</h2>
      <form onSubmit={onSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <input
          className={field}
          placeholder="School name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <input
          className={field}
          placeholder="District / island"
          value={district}
          onChange={(e) => setDistrict(e.target.value)}
        />
        <input
          className={field}
          type="email"
          placeholder="Contact email (optional)"
          value={contactEmail}
          onChange={(e) => setContactEmail(e.target.value)}
        />
        {error && (
          <div className="sm:col-span-3">
            <ErrorNote message={error} />
          </div>
        )}
        <div className="sm:col-span-3">
          <Button type="submit" disabled={busy || !name.trim()}>
            {busy ? "Registering…" : "Register"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

export default function SchoolsPage() {
  const schools = useQuery({ queryKey: ["schools"], queryFn: listSchools });
  const [justRegistered, setJustRegistered] = useState<SchoolWithToken | null>(null);

  return (
    <div className="space-y-6">
      <PageHeader title="Schools" subtitle="Every school this install can see." />

      <RegisterForm onDone={setJustRegistered} />

      {justRegistered && (
        <Card className="p-5 border-l-4 border-l-emerald-500">
          <h2 className="text-sm font-semibold">
            {justRegistered.name} — sync token (shown once)
          </h2>
          <p className="mt-1 text-sm text-[var(--campus-muted)]">
            Give this token, and the School ID below, to whoever runs this
            school&apos;s own Campus install, for their <code>manage link_central</code> step.
            It cannot be shown again — only rotated.
          </p>
          <div className="mt-3 space-y-1 font-mono text-sm">
            <div>School ID: {justRegistered.id}</div>
            <div className="break-all">Token: {justRegistered.sync_token}</div>
          </div>
        </Card>
      )}

      {schools.isLoading ? (
        <Spinner />
      ) : schools.isError ? (
        <ErrorNote message={apiMessage(schools.error)} />
      ) : (
        <Table
          columns={[
            {
              header: "Name",
              cell: (s) => <Link href={`/schools/detail/?id=${s.id}`}>{s.name}</Link>,
            },
            { header: "District", cell: (s) => s.district || "—" },
            {
              header: "Sync status",
              cell: (s) => <Badge tone={STATUS_TONE[s.sync_status]}>{label(s.sync_status)}</Badge>,
            },
            { header: "Last synced", cell: (s) => date(s.last_synced_at) },
            { header: "Active", cell: (s) => (s.active ? "Yes" : "No") },
          ]}
          rows={schools.data ?? []}
          empty="No schools registered yet."
        />
      )}
    </div>
  );
}
