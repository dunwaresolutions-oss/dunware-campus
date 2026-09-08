"use client";

import { useEffect, useState } from "react";
import { useAll, useList, useQueryParam, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { NestedList } from "@/components/NestedList";
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
import { RecordForm } from "@/components/RecordForm";
import { act, create, retrieve } from "@/lib/resource";
import { useQueryClient } from "@tanstack/react-query";
import { date, datetime, label } from "@/lib/format";

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

const STATUS = ["PROSPECTIVE", "ENROLLED", "WITHDRAWN", "GRADUATED"];
const statusTone = (s: string) =>
  s === "ENROLLED" ? "green" : s === "WITHDRAWN" ? "red" : "neutral";

export default function PeoplePage() {
  const [tab, setTab] = useState("students");
  const [detail, setDetail] = useState<Student | null>(null);
  const paramTab = useQueryParam("tab");
  const focusId = useQueryParam("focus");

  useEffect(() => {
    if (paramTab) setTab(paramTab);
  }, [paramTab]);
  useEffect(() => {
    if (!focusId) return;
    setTab("students");
    retrieve<Student>("students", focusId).then(setDetail).catch(() => {});
  }, [focusId]);
  const groups = useAll<Group>("groups");
  const groupOpts = options(groups.data, (g) => g.name);
  const guardiansAll = useAll<{
    id: string;
    first_name: string;
    last_name: string;
  }>("guardians");
  const guardianOpts = options(
    guardiansAll.data,
    (g) => `${g.first_name} ${g.last_name}`,
  );

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
          fields={studentFields}
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
          extraRowActions={(row) => (
            <Button size="sm" variant="ghost" onClick={() => setDetail(row)}>
              Open
            </Button>
          )}
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
        />
      )}

      {tab === "guardians" && (
        <CrudPanel
          resource="guardians"
          singular="guardian"
          columns={[
            {
              header: "Name",
              cell: (g) => `${g.first_name} ${g.last_name}`,
            },
            {
              header: "Children",
              cell: (g) => {
                const kids = (g.children as
                  | { id: string; name: string; relationship: string }[]
                  | undefined) ?? [];
                if (kids.length === 0)
                  return <span className="text-[var(--campus-muted)]">—</span>;
                return (
                  <span className="flex flex-wrap gap-1">
                    {kids.map((k) => (
                      <Badge key={k.id} tone="neutral">
                        {k.name}
                        <span className="ml-1 opacity-60">
                          {label(k.relationship)}
                        </span>
                      </Badge>
                    ))}
                  </span>
                );
              },
            },
            { header: "Email", cell: (g) => (g.email as string) || "—" },
            { header: "Phone", cell: (g) => (g.phone as string) || "—" },
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
          extraRowActions={(row, reload) =>
            row.user ? null : (
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

      <Modal
        open={!!detail}
        onClose={() => setDetail(null)}
        title={detail?.display_name || "Student"}
        wide
      >
        {detail && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
              <div className="text-[var(--campus-muted)]">Date of birth</div>
              <div>{date(detail.date_of_birth)}</div>
              <div className="text-[var(--campus-muted)]">Status</div>
              <div>{label(detail.status)}</div>
              <div className="text-[var(--campus-muted)]">Group</div>
              <div>{detail.primary_group_name || "—"}</div>
              <div className="text-[var(--campus-muted)]">Pronouns</div>
              <div>{detail.pronouns || "—"}</div>
            </div>

            <NestedList
              resource="guardian-links"
              parentKey="student"
              parentId={detail.id}
              title="Guardians"
              render={(r) => (
                <span>
                  {(r.guardian_name as string) || `#${r.guardian}`} ·{" "}
                  <span className="text-[var(--campus-muted)]">
                    {label(r.relationship as string)}
                  </span>
                  {r.can_pickup ? " · pickup" : ""}
                  {r.has_custody ? " · custody" : ""}
                </span>
              )}
              addFields={[
                {
                  name: "guardian",
                  label: "Guardian",
                  type: "select",
                  required: true,
                  options: guardianOpts,
                },
                {
                  name: "relationship",
                  label: "Relationship",
                  type: "select",
                  required: true,
                  options: [
                    "MOTHER",
                    "FATHER",
                    "PARENT",
                    "GRANDPARENT",
                    "LEGAL_GUARDIAN",
                    "FOSTER",
                    "OTHER",
                  ].map((v) => ({ value: v, label: label(v) })),
                },
                { name: "is_primary_contact", label: "Primary contact", type: "checkbox" },
                { name: "has_custody", label: "Has custody", type: "checkbox" },
                { name: "can_pickup", label: "Can pick up", type: "checkbox" },
                { name: "receives_communications", label: "Gets communications", type: "checkbox" },
                { name: "lives_with", label: "Lives with", type: "checkbox" },
              ]}
            />

            <NestedList
              resource="emergency-contacts"
              parentKey="student"
              parentId={detail.id}
              title="Emergency contacts"
              render={(r) => (
                <span>
                  {r.name as string} · {r.relationship as string} ·{" "}
                  {(r.phone as string) || "no phone"}
                </span>
              )}
              addFields={[
                { name: "name", label: "Name", required: true },
                { name: "relationship", label: "Relationship", required: true },
                { name: "phone", label: "Phone" },
                { name: "alt_phone", label: "Alt phone" },
                { name: "priority", label: "Priority", type: "number" },
              ]}
            />

            <NestedList
              resource="authorized-pickups"
              parentKey="student"
              parentId={detail.id}
              title="Authorized pickups"
              render={(r) => (
                <span>
                  {r.name as string} · {r.relationship as string}
                  {r.active ? "" : " (inactive)"}
                </span>
              )}
              addFields={[
                { name: "name", label: "Name", required: true },
                { name: "relationship", label: "Relationship", required: true },
                { name: "phone", label: "Phone" },
                { name: "note", label: "Note" },
                { name: "active", label: "Active", type: "checkbox" },
              ]}
            />

            <NestedList
              resource="observations"
              parentKey="student"
              parentId={detail.id}
              title="Observations"
              render={(r) => (
                <span>
                  <span className="text-[var(--campus-muted)]">
                    {datetime(r.occurred_at as string)}
                  </span>{" "}
                  · {label(r.category as string)} — {r.body as string}
                </span>
              )}
              addFields={[
                {
                  name: "category",
                  label: "Category",
                  type: "select",
                  required: true,
                  options: [
                    "DEVELOPMENTAL",
                    "BEHAVIOURAL",
                    "ACADEMIC",
                    "INCIDENT",
                    "MEDICAL",
                    "GENERAL",
                  ].map((v) => ({ value: v, label: label(v) })),
                },
                { name: "occurred_at", label: "When", type: "datetime", required: true },
                { name: "body", label: "Note", type: "textarea", required: true },
                { name: "visible_to_guardians", label: "Visible to guardians", type: "checkbox" },
              ]}
            />

            <NestedList
              resource="health/conditions"
              parentKey="student"
              parentId={detail.id}
              title="Health — conditions"
              render={(r) => (
                <span>
                  <span className="font-medium">{r.name as string}</span>
                  {r.ongoing ? " · ongoing" : ""}
                  {r.details ? ` — ${r.details as string}` : ""}
                </span>
              )}
              addFields={[
                { name: "name", label: "Condition", required: true },
                { name: "details", label: "Details (encrypted)", type: "textarea" },
                { name: "diagnosed_on", label: "Diagnosed on", type: "date" },
                { name: "ongoing", label: "Ongoing", type: "checkbox" },
              ]}
            />
            <NestedList
              resource="health/allergies"
              parentKey="student"
              parentId={detail.id}
              title="Health — allergies"
              render={(r) => (
                <span>
                  <span className="font-medium">{r.allergen as string}</span> —{" "}
                  <span className="text-[var(--campus-muted)]">
                    {label(r.severity as string)}
                  </span>
                  {r.epipen_required ? " · EpiPen" : ""}
                  {r.reaction ? ` — ${r.reaction as string}` : ""}
                </span>
              )}
              addFields={[
                { name: "allergen", label: "Allergen (encrypted)", required: true },
                { name: "reaction", label: "Reaction (encrypted)", type: "textarea" },
                {
                  name: "severity",
                  label: "Severity",
                  type: "select",
                  required: true,
                  options: ["MILD", "MODERATE", "SEVERE", "ANAPHYLAXIS"].map(
                    (v) => ({ value: v, label: label(v) }),
                  ),
                },
                { name: "epipen_required", label: "EpiPen required", type: "checkbox" },
              ]}
            />
            <NestedList
              resource="health/medications"
              parentKey="student"
              parentId={detail.id}
              title="Health — medications"
              render={(r) => (
                <span>
                  <span className="font-medium">{r.name as string}</span>
                  {r.dose ? ` ${r.dose as string}` : ""}
                  {r.schedule ? ` · ${r.schedule as string}` : ""}
                  {r.prn ? " · PRN" : ""}
                </span>
              )}
              addFields={[
                { name: "name", label: "Medication (encrypted)", required: true },
                { name: "dose", label: "Dose (encrypted)" },
                { name: "schedule", label: "Schedule (encrypted)" },
                {
                  name: "route",
                  label: "Route",
                  type: "select",
                  options: [
                    "ORAL",
                    "TOPICAL",
                    "INHALED",
                    "INJECTION",
                    "OTHER",
                  ].map((v) => ({ value: v, label: label(v) })),
                },
                { name: "prn", label: "As needed (PRN)", type: "checkbox" },
                { name: "prescriber", label: "Prescriber (encrypted)" },
                { name: "starts_on", label: "Starts", type: "date" },
                { name: "ends_on", label: "Ends", type: "date" },
              ]}
            />
            <NestedList
              resource="health/action-plans"
              parentKey="student"
              parentId={detail.id}
              title="Health — action plans"
              render={(r) => (
                <span>
                  <span className="font-medium">
                    {label(r.kind as string)}
                  </span>
                  {r.review_by ? ` · review by ${date(r.review_by as string)}` : ""}
                </span>
              )}
              addFields={[
                {
                  name: "kind",
                  label: "Kind",
                  type: "select",
                  required: true,
                  options: [
                    "ANAPHYLAXIS",
                    "ASTHMA",
                    "SEIZURE",
                    "DIABETES",
                    "OTHER",
                  ].map((v) => ({ value: v, label: label(v) })),
                },
                { name: "plan", label: "Plan (encrypted)", type: "textarea", required: true },
                { name: "effective_from", label: "Effective from", type: "date" },
                { name: "review_by", label: "Review by", type: "date" },
              ]}
            />

            <NestedList
              resource="documents"
              parentKey="student"
              parentId={detail.id}
              title="Documents"
              render={(r) => (
                <a
                  href={(r.download_url as string) || "#"}
                  className="text-[var(--campus-accent)] hover:underline"
                >
                  {r.title as string} ({label(r.kind as string)})
                </a>
              )}
              addFields={[
                { name: "title", label: "Title", required: true },
                {
                  name: "kind",
                  label: "Kind",
                  type: "select",
                  required: true,
                  options: [
                    "BIRTH_CERTIFICATE",
                    "IMMUNIZATION",
                    "CUSTODY_ORDER",
                    "IEP",
                    "PHOTO",
                    "CONSENT_FORM",
                    "OTHER",
                  ].map((v) => ({ value: v, label: label(v) })),
                },
                { name: "file", label: "File", type: "file", required: true },
              ]}
            />

            <StudentConsents studentId={detail.id} />
          </div>
        )}
      </Modal>
    </div>
  );
}

const CONSENT_KINDS = [
  "PHOTO",
  "MEDIA",
  "FIELD_TRIP",
  "DATA_SHARING",
  "MEDICAL_TREATMENT",
  "TECHNOLOGY",
  "SUNSCREEN",
];

function StudentConsents({ studentId }: { studentId: string }) {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const q = useList<{
    id: string;
    kind: string;
    version: string;
    granted: boolean;
    granted_by_name: string;
    recorded_at: string;
  }>("consents", { student: studentId });
  const rows = q.data?.results ?? [];
  const reload = () =>
    qc.invalidateQueries({ queryKey: ["list", "consents"] });

  return (
    <div className="rounded-md border border-[var(--campus-line)]">
      <div className="flex items-center justify-between border-b border-[var(--campus-line)] px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
          Consents
        </span>
        <Button size="sm" variant="subtle" onClick={() => setAdding(true)}>
          + Record
        </Button>
      </div>

      {q.isLoading ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <div className="px-3 py-5 text-center text-sm text-[var(--campus-muted)]">
          No consent decisions recorded.
        </div>
      ) : (
        <ul className="divide-y divide-[var(--campus-line)] text-sm">
          {rows.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-2 px-3 py-2">
              <span>
                {label(r.kind)}
                {r.version && r.version !== "1" ? ` · v${r.version}` : ""}
                {r.granted_by_name ? (
                  <span className="text-[var(--campus-muted)]"> · {r.granted_by_name}</span>
                ) : null}
              </span>
              <span className="flex items-center gap-2">
                <Badge tone={r.granted ? "green" : "red"}>
                  {r.granted ? "Granted" : "Withheld"}
                </Badge>
                <span className="text-xs text-[var(--campus-muted)]">
                  {date(r.recorded_at)}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}

      <Modal open={adding} onClose={() => setAdding(false)} title="Record a consent decision">
        <RecordForm
          fields={[
            {
              name: "kind",
              label: "Kind",
              type: "select",
              required: true,
              options: CONSENT_KINDS.map((v) => ({ value: v, label: label(v) })),
            },
            { name: "granted", label: "Granted", type: "checkbox" },
            { name: "granted_by_name", label: "Recorded on behalf of" },
            { name: "version", label: "Form version", placeholder: "1" },
          ]}
          submitLabel="Record"
          onSubmit={async (values) => {
            await create("consents", {
              ...values,
              student: studentId,
              version: values.version || "1",
            });
            setAdding(false);
            reload();
          }}
          onCancel={() => setAdding(false)}
        />
      </Modal>
    </div>
  );
}

function ChangeRequests({
  guardianName,
}: {
  guardianName: (id: unknown) => string;
}) {
  const qc = useQueryClient();
  const [status, setStatus] = useState("PENDING");
  const q = useList<{
    id: string;
    guardian: string;
    field: string;
    current_value: string | null;
    proposed_value: string;
    reason: string;
    status: string;
  }>("portal/contact-change-requests", { status });
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
              cell: (r) =>
                r.status === "PENDING" ? (
                  <span
                    className="flex justify-end gap-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <ActionButton
                      label="Approve"
                      confirm="Apply this change to the guardian's record?"
                      onRun={() =>
                        act(
                          "portal/contact-change-requests",
                          r.id,
                          "approve",
                        )
                      }
                      onDone={reload}
                    />
                    <ActionButton
                      label="Reject"
                      variant="ghost"
                      fields={[{ name: "note", label: "Note (optional)" }]}
                      onRun={(v) =>
                        act(
                          "portal/contact-change-requests",
                          r.id,
                          "reject",
                          v,
                        )
                      }
                      onDone={reload}
                    />
                  </span>
                ) : (
                  <Badge tone={r.status === "APPROVED" ? "green" : "red"}>
                    {label(r.status)}
                  </Badge>
                ),
            },
          ]}
        />
      )}
    </Card>
  );
}
