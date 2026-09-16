"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAll, useList, useQueryParam, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { ActionButton } from "@/components/ActionButton";
import {
  PageHeader,
  Tabs,
  Badge,
  Button,
  Card,
  Spinner,
  Table,
} from "@/components/ui";
import { Modal } from "@/components/Modal";
import { act } from "@/lib/resource";
import { api } from "@/lib/api";
import { RecordDetail } from "@/components/RecordDetail";
import { useQueryClient } from "@tanstack/react-query";
import { useToast } from "@/components/Toast";
import { datetime, date, label, apiMessage, yn } from "@/lib/format";

interface Group {
  id: number;
  name: string;
}
interface Student {
  id: string;
  display_name: string;
  first_name: string;
  last_name: string;
  date_of_birth: string | null;
  status: string;
  primary_group: number | null;
  primary_group_name?: string;
  guardian_count?: number;
  student_number?: string;
  pronouns?: string;
}

interface GuardianChild {
  id: string;
  name: string;
  relationship: string;
}

function guardianChildren(g: Record<string, unknown>): GuardianChild[] {
  return (g.children as GuardianChild[] | undefined) ?? [];
}

const STATUS = ["PROSPECTIVE", "ENROLLED", "WITHDRAWN", "GRADUATED"];
const statusTone = (s: string) =>
  s === "ENROLLED" ? "green" : s === "WITHDRAWN" ? "red" : "neutral";

export default function PeoplePage() {
  const router = useRouter();
  const [tab, setTab] = useState("students");
  const paramTab = useQueryParam("tab");
  const focusId = useQueryParam("focus");

  useEffect(() => {
    if (paramTab) setTab(paramTab);
  }, [paramTab]);
  useEffect(() => {
    if (focusId) router.replace(`/people/student?id=${focusId}`);
  }, [focusId, router]);
  const groups = useAll<Group>("groups");
  const groupOpts = options(groups.data, (g) => g.name);
  const guardiansAll = useAll<{
    id: string;
    first_name: string;
    last_name: string;
  }>("guardians");

  const studentFields = [
    { name: "first_name", label: "First name", required: true },
    { name: "last_name", label: "Last name", required: true },
    { name: "preferred_name", label: "Preferred name" },
    { name: "date_of_birth", label: "Date of birth", type: "date" as const },
    { name: "pronouns", label: "Pronouns" },
    { name: "student_number", label: "Student number" },
    {
      name: "status",
      label: "Status",
      type: "select" as const,
      options: STATUS.map((s) => ({ value: s, label: label(s) })),
    },
    {
      name: "primary_group",
      label: "Primary group",
      type: "select" as const,
      options: groupOpts,
    },
    { name: "government_id", label: "Government ID (encrypted)" },
    { name: "custody_notes", label: "Custody notes (encrypted)", type: "textarea" as const },
    { name: "legal_hold", label: "Legal hold (blocks erasure)", type: "checkbox" as const },
  ];

  return (
    <div>
      <PageHeader
        title="Students"
        subtitle="The child record — profile, guardians, emergency contacts, authorized pickups, observations, health, and documents."
      />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "students", label: "Students" },
          { key: "groups", label: "Groups" },
          { key: "guardians", label: "Guardians" },
          { key: "changes", label: "Change requests" },
        ]}
      />

      {tab === "students" && (
        <CrudPanel<Student>
          resource="students"
          singular="student"
          searchable
          searchPlaceholder="Search students by name or student number…"
          fields={studentFields}
          onRowOpen={(s) => router.push(`/people/student?id=${s.id}`)}
          columns={[
            { header: "Name", cell: (s) => s.display_name || `${s.first_name} ${s.last_name}` },
            { header: "DOB", cell: (s) => date(s.date_of_birth) },
            {
              header: "Group",
              cell: (s) =>
                s.primary_group_name ||
                groups.data?.find((g) => g.id === s.primary_group)?.name ||
                "—",
            },
            { header: "Guardians", cell: (s) => s.guardian_count ?? 0 },
            {
              header: "Status",
              cell: (s) => (
                <Badge tone={statusTone(s.status)}>{label(s.status)}</Badge>
              ),
            },
          ]}
        />
      )}

      {tab === "groups" && (
        <CrudPanel
          resource="groups"
          singular="group"
          columns={[
            { header: "Name", cell: (g) => g.name as string },
            { header: "Kind", cell: (g) => label(g.kind as string) },
            { header: "Stage", cell: (g) => (g.stage_label as string) || "—" },
            { header: "Capacity", cell: (g) => (g.capacity as number) ?? "—" },
            {
              header: "Enrolled",
              cell: (g) => (g.active_enrolment_count as number) ?? 0,
            },
          ]}
          fields={[
            { name: "name", label: "Name", required: true },
            {
              name: "kind",
              label: "Kind",
              type: "select",
              options: ["ROOM", "CLASS", "SECTION"].map((v) => ({
                value: v,
                label: label(v),
              })),
            },
            { name: "stage_label", label: "Stage label", placeholder: "Grade 4 / Toddler / SNC2D" },
            { name: "capacity", label: "Capacity", type: "number" },
            { name: "active", label: "Active", type: "checkbox" },
          ]}
          detailTitle={(g) => `Group — ${g.name as string}`}
          detailFields={[
            { label: "Name", value: (g) => g.name as string },
            { label: "Kind", value: (g) => label(g.kind as string) },
            { label: "Stage label", value: (g) => (g.stage_label as string) || "—" },
            { label: "Capacity", value: (g) => (g.capacity as number) ?? "—" },
            {
              label: "Enrolled now",
              value: (g) => (g.active_enrolment_count as number) ?? 0,
            },
            { label: "Active", value: (g) => yn(g.active) },
          ]}
        />
      )}

      {tab === "guardians" && (
        <CrudPanel
          resource="guardians"
          singular="guardian"
          searchable
          searchPlaceholder="Search guardians by name or email…"
          columns={[
            {
              header: "Child(ren)",
              cell: (g) => {
                const kids = guardianChildren(g);
                if (kids.length === 0)
                  return <span className="text-[var(--campus-muted)]">—</span>;
                return (
                  <span className="flex flex-wrap gap-1">
                    {kids.map((k) => (
                      <Badge key={k.id} tone="neutral">
                        {k.name}
                      </Badge>
                    ))}
                  </span>
                );
              },
            },
            {
              header: "Guardian name",
              cell: (g) => `${g.first_name} ${g.last_name}`,
            },
            {
              header: "Type",
              cell: (g) => {
                const kids = guardianChildren(g);
                if (kids.length === 0)
                  return <span className="text-[var(--campus-muted)]">—</span>;
                // Aligned by position with the Child(ren) column above — one
                // relationship per linked child, in the same order, so a
                // guardian with several children (possibly different
                // relationships to each) still reads unambiguously.
                return (
                  <span className="flex flex-wrap gap-1">
                    {kids.map((k) => (
                      <Badge key={k.id} tone="sky">
                        {label(k.relationship)}
                      </Badge>
                    ))}
                  </span>
                );
              },
            },
            { header: "Email", cell: (g) => (g.email as string) || "—" },
            { header: "Phone", cell: (g) => (g.phone as string) || "—" },
            { header: "Address", cell: (g) => (g.address as string) || "—" },
            {
              header: "Portal",
              cell: (g) =>
                g.user ? <Badge tone="green">has login</Badge> : "—",
            },
          ]}
          fields={[
            { name: "first_name", label: "First name", required: true },
            { name: "last_name", label: "Last name", required: true },
            { name: "email", label: "Email" },
            { name: "phone", label: "Phone (encrypted)" },
            { name: "address", label: "Address (encrypted)", type: "textarea" },
          ]}
          detailTitle={(g) => `Guardian — ${g.first_name} ${g.last_name}`}
          detailFields={[
            {
              label: "Name",
              value: (g) => `${g.first_name} ${g.last_name}`.trim(),
            },
            { label: "Email", value: (g) => (g.email as string) || "—" },
            { label: "Phone", value: (g) => (g.phone as string) || "—" },
            {
              label: "Portal login",
              value: (g) => (g.user ? "Yes" : "No — use Create portal login"),
            },
            {
              label: "Children",
              long: true,
              value: (g) => {
                const kids = guardianChildren(g);
                return kids.length
                  ? kids
                      .map((k) => `${k.name} (${label(k.relationship)})`)
                      .join("\n")
                  : "—";
              },
            },
            { label: "Address", value: (g) => (g.address as string) || "—", long: true },
          ]}
          extraRowActions={(row, reload) =>
            row.user ? (
              <GuardianLoginActions userId={row.user as string} reload={reload} />
            ) : (
              <ActionButton
                label="Create portal login"
                title="Give this guardian a portal account"
                fields={[
                  { name: "username", label: "Username", required: true },
                  {
                    name: "password",
                    label: "Password (12+ chars)",
                    required: true,
                  },
                ]}
                onRun={(v) =>
                  act("guardians", row.id as string, "create_login", v)
                }
                onDone={reload}
              />
            )
          }
        />
      )}

      {tab === "changes" && (
        <ChangeRequests
          guardianName={(id: unknown) => {
            const g = guardiansAll.data?.find((x) => x.id === id);
            return g ? `${g.first_name} ${g.last_name}` : String(id);
          }}
        />
      )}

    </div>
  );
}

function GuardianLoginActions({
  userId,
  reload,
}: {
  userId: string;
  reload: () => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState<string | null>(null);

  async function resetPassword() {
    setBusy("reset");
    try {
      const res = await api<{ username: string; new_password: string }>(
        `/auth/portal-logins/${userId}/`,
        { method: "POST" },
      );
      setNewPassword(res.new_password);
    } catch (e) {
      toast("error", apiMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function removeLogin() {
    if (!window.confirm("Remove this guardian's portal login? They keep their record — only the login goes.")) return;
    setBusy("delete");
    try {
      await api(`/auth/portal-logins/${userId}/`, { method: "DELETE" });
      toast("success", "Portal login removed");
      reload();
    } catch (e) {
      toast("error", apiMessage(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <Button size="sm" variant="ghost" disabled={!!busy} onClick={resetPassword}>
        Reset password
      </Button>
      <Button size="sm" variant="ghost" disabled={!!busy} onClick={removeLogin}>
        Remove login
      </Button>
      <Modal
        open={newPassword != null}
        onClose={() => setNewPassword(null)}
        title="Password reset"
      >
        <div className="space-y-3 text-sm">
          <p>Give this to the guardian directly — it won&apos;t be shown again:</p>
          <code className="block rounded-md border border-[var(--campus-line)] bg-black/[0.03] px-3 py-2 text-base dark:bg-white/[0.04]">
            {newPassword}
          </code>
          <div className="flex justify-end">
            <Button size="sm" onClick={() => setNewPassword(null)}>
              Done
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}

interface ChangeReq {
  id: string;
  guardian: string;
  field: string;
  current_value: string | null;
  proposed_value: string;
  reason: string;
  status: string;
  review_note?: string;
  reviewed_at?: string | null;
}

function ChangeRequests({
  guardianName,
}: {
  guardianName: (id: unknown) => string;
}) {
  const qc = useQueryClient();
  const [status, setStatus] = useState("PENDING");
  const [detail, setDetail] = useState<ChangeReq | null>(null);
  const q = useList<ChangeReq>("portal/contact-change-requests", { status });
  const reload = () =>
    qc.invalidateQueries({ queryKey: ["list", "portal/contact-change-requests"] });

  return (
    <Card>
      <div className="flex items-center gap-2 border-b border-[var(--campus-line)] p-3 text-sm">
        <span className="text-[var(--campus-muted)]">Show:</span>
        {["PENDING", "APPROVED", "REJECTED"].map((s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className={`rounded-md px-2 py-1 text-xs ${
              status === s
                ? "bg-[var(--campus-accent-soft)] text-[var(--campus-accent)]"
                : "text-[var(--campus-muted)] hover:text-[var(--campus-fg)]"
            }`}
          >
            {label(s)}
          </button>
        ))}
      </div>
      {q.isLoading ? (
        <Spinner />
      ) : (
        <Table
          rows={q.data?.results ?? []}
          empty={`No ${label(status).toLowerCase()} requests.`}
          onRowClick={(r) => setDetail(r)}
          columns={[
            { header: "Guardian", cell: (r) => guardianName(r.guardian) },
            { header: "Field", cell: (r) => label(r.field) },
            { header: "Current", cell: (r) => r.current_value || "—" },
            { header: "Proposed", cell: (r) => r.proposed_value },
            {
              header: "Reason",
              cell: (r) => r.reason || "—",
              className: "max-w-xs truncate",
            },
            {
              header: "",
              className: "text-right whitespace-nowrap",
              cell: (r) => (
                <span
                  className="flex justify-end gap-1"
                  onClick={(e) => e.stopPropagation()}
                >
                  {r.status === "PENDING" ? (
                    <>
                      <ActionButton
                        label="Approve"
                        confirm="Apply this change to the guardian's record?"
                        onRun={() =>
                          act("portal/contact-change-requests", r.id, "approve")
                        }
                        onDone={reload}
                      />
                      <ActionButton
                        label="Reject"
                        variant="ghost"
                        fields={[{ name: "note", label: "Note (optional)" }]}
                        onRun={(v) =>
                          act("portal/contact-change-requests", r.id, "reject", v)
                        }
                        onDone={reload}
                      />
                    </>
                  ) : (
                    <Badge tone={r.status === "APPROVED" ? "green" : "red"}>
                      {label(r.status)}
                    </Badge>
                  )}
                </span>
              ),
            },
          ]}
        />
      )}

      <Modal
        open={!!detail}
        onClose={() => setDetail(null)}
        title="Contact-change request"
        wide
      >
        {detail && (
          <RecordDetail
            fields={[
              { label: "Guardian", value: () => guardianName(detail.guardian) },
              { label: "Field", value: () => label(detail.field) },
              { label: "Status", value: () => label(detail.status) },
              {
                label: "Reviewed",
                value: () =>
                  detail.reviewed_at ? datetime(detail.reviewed_at) : "—",
              },
              {
                label: "Current value",
                long: true,
                value: () => detail.current_value || "—",
              },
              {
                label: "Proposed value",
                long: true,
                value: () => detail.proposed_value || "—",
              },
              {
                label: "Reason given",
                long: true,
                value: () => detail.reason || "—",
              },
              {
                label: "Review note",
                long: true,
                value: () => detail.review_note || "—",
              },
            ]}
            row={detail as unknown as Record<string, unknown>}
          />
        )}
      </Modal>
    </Card>
  );
}
