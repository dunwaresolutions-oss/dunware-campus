"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useQueryParam, useList, useAll, options } from "@/lib/hooks";
import { retrieve, patch, create } from "@/lib/resource";
import { api } from "@/lib/api";
import { ScheduleCalendar } from "@/components/ScheduleCalendar";
import { NestedList } from "@/components/NestedList";
import { RecordForm } from "@/components/RecordForm";
import { useToast } from "@/components/Toast";
import { Modal } from "@/components/Modal";
import { Card, Tabs, Badge, Button, Spinner } from "@/components/ui";
import { date, datetime, time, label, apiMessage } from "@/lib/format";

interface Student {
  id: string;
  display_name: string;
  first_name: string;
  last_name: string;
  preferred_name?: string;
  date_of_birth: string | null;
  pronouns?: string;
  student_number?: string;
  status: string;
  primary_group: string | null;
  primary_group_name?: string;
  photo_url: string | null;
  government_id_type?: string;
  government_id?: string;
  custody_notes?: string;
  legal_hold?: boolean;
}

const STATUS = ["PROSPECTIVE", "ENROLLED", "WITHDRAWN", "GRADUATED"];
const GOV_ID_TYPES = [
  "NATIONAL_ID", "PASSPORT", "BIRTH_CERTIFICATE",
  "SOCIAL_INSURANCE", "VOTER_ID", "OTHER",
];
const statusTone = (s: string) =>
  s === "ENROLLED" ? "green" : s === "WITHDRAWN" ? "red" : "neutral";

function ageOf(dob: string | null | undefined): string {
  if (!dob) return "";
  const b = new Date(dob);
  const now = new Date();
  let y = now.getFullYear() - b.getFullYear();
  const m = now.getMonth() - b.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < b.getDate())) y--;
  return `${y} yr`;
}

const TABS = [
  "overview", "contacts", "health", "iep", "classes", "timetable",
  "attendance", "assessment", "discipline", "documents", "consents",
] as const;
type Tab = (typeof TABS)[number];

export default function StudentProfilePage() {
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const id = useQueryParam("id");
  const [tab, setTab] = useState<Tab>("overview");
  const fileRef = useRef<HTMLInputElement>(null);
  const [busyPhoto, setBusyPhoto] = useState(false);

  const q = useQuery({
    queryKey: ["student", id],
    queryFn: () => retrieve<Student>("students", id as string),
    enabled: !!id,
  });
  const adj = useQuery({
    queryKey: ["student-adjacent", id],
    queryFn: () => api<{ prev: string | null; next: string | null }>(`/students/${id}/adjacent/`),
    enabled: !!id,
  });
  const groups = useAll<{ id: string; name: string }>("groups");

  const s = q.data;

  async function onPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !s) return;
    setBusyPhoto(true);
    try {
      const fd = new FormData();
      fd.append("photo", file);
      const next = await api<Student>(`/students/${s.id}/`, { method: "PATCH", body: fd });
      qc.setQueryData(["student", id], next);
      toast("success", "Photo updated");
    } catch (err) {
      toast("error", apiMessage(err));
    } finally {
      setBusyPhoto(false);
    }
  }

  async function clearPhoto() {
    if (!s) return;
    setBusyPhoto(true);
    try {
      await api(`/students/${s.id}/photo/`, { method: "DELETE" });
      qc.setQueryData(["student", id], { ...s, photo_url: null });
      toast("success", "Photo removed");
    } catch (err) {
      toast("error", apiMessage(err));
    } finally {
      setBusyPhoto(false);
    }
  }

  if (!id) return <p className="p-6 text-sm text-[var(--campus-muted)]">No student selected.</p>;
  if (q.isLoading) return <Spinner />;
  if (q.isError || !s)
    return (
      <div className="p-6">
        <Button variant="ghost" onClick={() => router.push("/people/")}>
          ← Students
        </Button>
        <p className="mt-4 text-sm text-red-600">{apiMessage(q.error)}</p>
      </div>
    );

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <Button size="sm" variant="ghost" onClick={() => router.push("/people/")}>
          ← All students
        </Button>
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            disabled={!adj.data?.prev}
            onClick={() => adj.data?.prev && router.push(`/people/student?id=${adj.data.prev}`)}
          >
            ‹ Prev
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={!adj.data?.next}
            onClick={() => adj.data?.next && router.push(`/people/student?id=${adj.data.next}`)}
          >
            Next ›
          </Button>
        </div>
      </div>

      <Card className="mb-4 p-4">
        <div className="flex items-start gap-4">
          <div className="shrink-0">
            {s.photo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={s.photo_url}
                alt=""
                className="h-24 w-24 rounded-lg border border-[var(--campus-line)] object-cover"
              />
            ) : (
              <div className="grid h-24 w-24 place-items-center rounded-lg border border-dashed border-[var(--campus-line)] text-2xl font-semibold text-[var(--campus-muted)]">
                {(s.first_name?.[0] ?? "") + (s.last_name?.[0] ?? "")}
              </div>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={onPhoto}
            />
            <div className="mt-1 flex justify-center gap-2 text-[11px]">
              <button
                className="text-[var(--campus-accent)] hover:underline disabled:opacity-50"
                disabled={busyPhoto}
                onClick={() => fileRef.current?.click()}
              >
                {s.photo_url ? "replace" : "add photo"}
              </button>
              {s.photo_url && (
                <button
                  className="text-[var(--campus-muted)] hover:underline disabled:opacity-50"
                  disabled={busyPhoto}
                  onClick={clearPhoto}
                >
                  remove
                </button>
              )}
            </div>
          </div>

          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-semibold tracking-tight">{s.display_name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-[var(--campus-muted)]">
              <Badge tone={statusTone(s.status)}>{label(s.status)}</Badge>
              {s.student_number && <span>#{s.student_number}</span>}
              <span>{s.primary_group_name || groups.data?.find((g) => g.id === s.primary_group)?.name || "no group"}</span>
              {s.date_of_birth && <span>{date(s.date_of_birth)} · {ageOf(s.date_of_birth)}</span>}
              {s.pronouns && <span>{s.pronouns}</span>}
              {s.legal_hold && <Badge tone="amber">legal hold</Badge>}
            </div>
          </div>
        </div>
      </Card>

      <Tabs
        active={tab}
        onChange={(t) => setTab(t as Tab)}
        tabs={TABS.map((t) => ({ key: t, label: label(t) }))}
      />

      <div className="mt-4">
        {tab === "overview" && (
          <Card className="p-4">
            <RecordForm
              fields={[
                { name: "first_name", label: "First name", required: true },
                { name: "last_name", label: "Last name", required: true },
                { name: "preferred_name", label: "Preferred name" },
                { name: "date_of_birth", label: "Date of birth", type: "date" },
                { name: "pronouns", label: "Pronouns" },
                { name: "student_number", label: "Student number" },
                {
                  name: "status",
                  label: "Status",
                  type: "select",
                  options: STATUS.map((v) => ({ value: v, label: label(v) })),
                },
                {
                  name: "primary_group",
                  label: "Primary group",
                  type: "select",
                  options: options(groups.data, (g) => g.name),
                },
                {
                  name: "government_id_type",
                  label: "Government ID type",
                  type: "select",
                  options: GOV_ID_TYPES.map((v) => ({ value: v, label: label(v) })),
                },
                { name: "government_id", label: "Government ID number (encrypted)" },
                { name: "custody_notes", label: "Custody notes (encrypted)", type: "textarea" },
                { name: "legal_hold", label: "Legal hold (blocks erasure)", type: "checkbox" },
              ]}
              initialValues={s as unknown as Record<string, unknown>}
              submitLabel="Save changes"
              onSubmit={async (v) => {
                const next = await patch<Student>("students", s.id, v);
                qc.setQueryData(["student", id], next);
                qc.invalidateQueries({ queryKey: ["list", "students"] });
                toast("success", "Saved");
              }}
              onCancel={() => {}}
            />
          </Card>
        )}

        {tab === "contacts" && (
          <div className="space-y-4">
            <Guardians studentId={s.id} />
            <NestedList
              resource="emergency-contacts"
              parentKey="student"
              parentId={s.id}
              title="Emergency contacts"
              render={(r) => (
                <span>
                  {r.name as string} · {r.relationship as string} · {(r.phone as string) || "no phone"}
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
              parentId={s.id}
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
          </div>
        )}

        {tab === "health" && (
          <div className="space-y-4">
            <NestedList
              resource="health/conditions"
              parentKey="student"
              parentId={s.id}
              title="Conditions"
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
              parentId={s.id}
              title="Allergies"
              render={(r) => (
                <span>
                  <span className="font-medium">{r.allergen as string}</span> —{" "}
                  <span className="text-[var(--campus-muted)]">{label(r.severity as string)}</span>
                  {r.epipen_required ? " · EpiPen" : ""}
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
                  options: ["MILD", "MODERATE", "SEVERE", "ANAPHYLAXIS"].map((v) => ({
                    value: v,
                    label: label(v),
                  })),
                },
                { name: "epipen_required", label: "EpiPen required", type: "checkbox" },
              ]}
            />
            <NestedList
              resource="health/medications"
              parentKey="student"
              parentId={s.id}
              title="Medications"
              render={(r) => (
                <span>
                  <span className="font-medium">{r.name as string}</span>
                  {r.dose ? ` ${r.dose as string}` : ""}
                  {r.prn ? " · PRN" : ""}
                </span>
              )}
              addFields={[
                { name: "name", label: "Medication (encrypted)", required: true },
                { name: "dose", label: "Dose (encrypted)" },
                { name: "schedule", label: "Schedule (encrypted)" },
                { name: "prn", label: "As needed (PRN)", type: "checkbox" },
              ]}
            />
            <NestedList
              resource="health/action-plans"
              parentKey="student"
              parentId={s.id}
              title="Action plans"
              render={(r) => (
                <span>
                  <span className="font-medium">{label(r.kind as string)}</span>
                  {r.review_by ? ` · review by ${date(r.review_by as string)}` : ""}
                </span>
              )}
              addFields={[
                {
                  name: "kind",
                  label: "Kind",
                  type: "select",
                  required: true,
                  options: ["ANAPHYLAXIS", "ASTHMA", "SEIZURE", "DIABETES", "OTHER"].map((v) => ({
                    value: v,
                    label: label(v),
                  })),
                },
                { name: "plan", label: "Plan (encrypted)", type: "textarea", required: true },
                { name: "effective_from", label: "Effective from", type: "date" },
                { name: "review_by", label: "Review by", type: "date" },
              ]}
            />
          </div>
        )}

        {tab === "iep" && (
          <div className="space-y-2">
            <RelList
              resource="ieps"
              studentId={s.id}
              render={(r) =>
                `${r.primary_concern || "IEP"} · ${label(String(r.status))} · ${r.goal_count ?? 0} goal(s)${r.review_date ? ` · review ${date(String(r.review_date))}` : ""}`
              }
              empty="No IEP on file."
            />
            <a
              href={`/iep?student=${s.id}`}
              className="inline-block text-sm text-[var(--campus-accent)] hover:underline"
            >
              Open in IEPs →
            </a>
          </div>
        )}

        {tab === "classes" && (
          <div className="space-y-4">
            <RelList
              resource="enrolments"
              studentId={s.id}
              title="Classes &amp; course sections"
              render={(r) => `${r.group_name ?? r.group} · ${label(String(r.status))} · from ${date(String(r.start_date))}${r.end_date ? ` to ${date(String(r.end_date))}` : ""}`}
              empty="Not enrolled in any group."
            />
            <RelList
              resource="bookings"
              studentId={s.id}
              title="After-school offerings"
              render={(r) => `${r.offering_title ?? "Offering"} · ${r.starts_at ? datetime(String(r.starts_at)) : "—"} · ${label(String(r.status))}`}
              empty="Not booked into any after-school offering."
            />
          </div>
        )}

        {tab === "timetable" && <Timetable studentId={s.id} groupId={s.primary_group} />}

        {tab === "attendance" && <StudentAttendance studentId={s.id} />}

        {tab === "assessment" && (
          <div className="space-y-4">
            <RelList resource="report-cards" studentId={s.id} title="Report cards" render={(r) => `${r.term_name ?? "term"} · ${label(String(r.status))}${r.released_at ? ` · released ${date(String(r.released_at))}` : ""}`} empty="No report cards." />
            <RelList resource="assessment-results" studentId={s.id} title="Assessment results" render={(r) => `${r.assessment_title ?? r.assessment} · ${r.mark ?? "—"}${r.max_mark ? ` / ${r.max_mark}` : ""}`} empty="No assessment results." />
          </div>
        )}

        {tab === "discipline" && (
          <div className="space-y-4">
            <RelList resource="incident-reports" studentId={s.id} title="Incident reports" render={(r) => `${datetime(String(r.occurred_at))} · ${label(String(r.category))} · sev ${r.severity ?? "—"} · ${label(String(r.status))}`} empty="No incident reports." />
            <NestedList
              resource="observations"
              parentKey="student"
              parentId={s.id}
              title="Observations"
              render={(r) => (
                <span>
                  <span className="text-[var(--campus-muted)]">{datetime(r.occurred_at as string)}</span>{" "}
                  · {label(r.category as string)} — {r.body as string}
                </span>
              )}
              addFields={[
                {
                  name: "category",
                  label: "Category",
                  type: "select",
                  required: true,
                  options: ["DEVELOPMENTAL", "BEHAVIOURAL", "ACADEMIC", "INCIDENT", "MEDICAL", "GENERAL"].map((v) => ({
                    value: v,
                    label: label(v),
                  })),
                },
                { name: "occurred_at", label: "When", type: "datetime", required: true },
                { name: "body", label: "Note", type: "textarea", required: true },
                { name: "visible_to_guardians", label: "Visible to guardians", type: "checkbox" },
              ]}
            />
          </div>
        )}

        {tab === "documents" && (
          <NestedList
            resource="documents"
            parentKey="student"
            parentId={s.id}
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
                options: ["BIRTH_CERTIFICATE", "IMMUNIZATION", "CUSTODY_ORDER", "IEP", "PHOTO", "CONSENT_FORM", "OTHER"].map((v) => ({
                  value: v,
                  label: label(v),
                })),
              },
              { name: "file", label: "File", type: "file", required: true },
            ]}
          />
        )}

        {tab === "consents" && <StudentConsents studentId={s.id} />}
      </div>
    </div>
  );
}

/* ---- helpers -------------------------------------------------------- */

function RelList({
  resource,
  studentId,
  render,
  empty,
  title,
}: {
  resource: string;
  studentId: string;
  render: (r: Record<string, unknown>) => string;
  empty: string;
  title?: string;
}) {
  const q = useList<Record<string, unknown>>(resource, { student: studentId });
  const rows = q.data?.results ?? [];
  return (
    <div className="rounded-md border border-[var(--campus-line)]">
      {title && (
        <div className="border-b border-[var(--campus-line)] px-3 py-2 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
          {title}
        </div>
      )}
      {q.isLoading ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <div className="px-3 py-5 text-center text-sm text-[var(--campus-muted)]">{empty}</div>
      ) : (
        <ul className="divide-y divide-[var(--campus-line)] text-sm">
          {rows.map((r) => (
            <li key={String(r.id)} className="px-3 py-2">
              {render(r)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const ATTENDANCE_STATUSES = ["PRESENT", "ABSENT", "LATE", "EXCUSED", "LEFT_EARLY", "EXPECTED"];

function StudentAttendance({ studentId }: { studentId: string }) {
  const [filter, setFilter] = useState("");
  const q = useList<{ id: string; date: string; status: string; group_name?: string }>(
    "attendance",
    { student: studentId },
  );
  const rows = q.data?.results ?? [];
  const totals = new Map<string, number>();
  for (const r of rows) totals.set(r.status, (totals.get(r.status) ?? 0) + 1);
  const shown = filter ? rows.filter((r) => r.status === filter) : rows;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {ATTENDANCE_STATUSES.filter((s) => totals.get(s)).map((s) => (
          <button
            key={s}
            onClick={() => setFilter(filter === s ? "" : s)}
            className={`rounded-full border px-2.5 py-1 text-xs ${
              filter === s
                ? "border-[var(--campus-accent)] bg-[var(--campus-accent-soft)] text-[var(--campus-accent)]"
                : "border-[var(--campus-line)] text-[var(--campus-muted)] hover:text-[var(--campus-fg)]"
            }`}
          >
            {label(s)}: {totals.get(s)}
          </button>
        ))}
        {filter && (
          <button
            onClick={() => setFilter("")}
            className="text-xs text-[var(--campus-accent)] hover:underline"
          >
            Clear filter
          </button>
        )}
      </div>
      <div className="rounded-md border border-[var(--campus-line)]">
        {q.isLoading ? (
          <Spinner />
        ) : shown.length === 0 ? (
          <div className="px-3 py-5 text-center text-sm text-[var(--campus-muted)]">
            {filter ? `No ${label(filter).toLowerCase()} records.` : "No attendance records."}
          </div>
        ) : (
          <ul className="divide-y divide-[var(--campus-line)] text-sm">
            {shown.map((r) => (
              <li key={r.id} className="px-3 py-2">
                {date(r.date)} · {label(r.status)}
                {r.group_name ? ` · ${r.group_name}` : ""}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Timetable({ studentId, groupId }: { studentId: string; groupId: string | null }) {
  const [open, setOpen] = useState<import("@/lib/calendar").CalendarSession | null>(null);
  if (!groupId)
    return (
      <div className="rounded-md border border-[var(--campus-line)] px-3 py-5 text-center text-sm text-[var(--campus-muted)]">
        No primary group — assign one on the Overview tab.
      </div>
    );
  return (
    <>
      <p className="mb-3 text-sm text-[var(--campus-muted)]">
        Every class this student is actually enrolled in — homeroom plus every
        course-of-study section — not just their homeroom block.
      </p>
      <ScheduleCalendar groups={[]} fixedStudentId={studentId} initialView="week" onOpenSession={setOpen} />
      <Modal
        open={!!open}
        onClose={() => setOpen(null)}
        title={open ? open.title || open.group_name || "Session" : "Session"}
      >
        {open && (
          <div className="space-y-1 text-sm">
            <div>{date(open.date)} · {time(open.start_time)}–{time(open.end_time)}</div>
            {open.room_name && <div className="text-[var(--campus-muted)]">{open.room_name}</div>}
            {open.status === "CANCELLED" && (
              <div className="text-red-600">
                Cancelled{open.cancelled_reason ? `: ${open.cancelled_reason}` : ""}
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}

function Guardians({ studentId }: { studentId: string }) {
  const guardiansAll = useAll<{ id: string; first_name: string; last_name: string }>("guardians");
  return (
    <NestedList
      resource="guardian-links"
      parentKey="student"
      parentId={studentId}
      title="Guardians"
      render={(r) => (
        <span>
          {(r.guardian_name as string) || `#${r.guardian}`} ·{" "}
          <span className="text-[var(--campus-muted)]">{label(r.relationship as string)}</span>
          {r.can_pickup ? " · pickup" : ""}
          {r.has_custody ? " · custody" : ""}
          {r.receives_communications ? "" : " · no comms"}
        </span>
      )}
      addFields={[
        {
          name: "guardian",
          label: "Guardian",
          type: "select",
          required: true,
          options: options(guardiansAll.data, (g) => `${g.first_name} ${g.last_name}`),
        },
        {
          name: "relationship",
          label: "Relationship",
          type: "select",
          required: true,
          options: ["MOTHER", "FATHER", "PARENT", "GRANDPARENT", "LEGAL_GUARDIAN", "FOSTER", "OTHER"].map((v) => ({
            value: v,
            label: label(v),
          })),
        },
        { name: "is_primary_contact", label: "Primary contact", type: "checkbox" },
        { name: "has_custody", label: "Has custody", type: "checkbox" },
        { name: "can_pickup", label: "Can pick up", type: "checkbox" },
        { name: "receives_communications", label: "Gets communications", type: "checkbox" },
        { name: "lives_with", label: "Lives with", type: "checkbox" },
      ]}
    />
  );
}

const CONSENT_KINDS = [
  "PHOTO", "MEDIA", "FIELD_TRIP", "DATA_SHARING",
  "MEDICAL_TREATMENT", "TECHNOLOGY", "SUNSCREEN",
];

function StudentConsents({ studentId }: { studentId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const q = useList<{
    id: string;
    kind: string;
    version: string;
    granted: boolean;
    granted_by_name: string;
    recorded_at: string;
  }>("consents", { student: studentId });
  const rows = q.data?.results ?? [];
  const reload = () => qc.invalidateQueries({ queryKey: ["list", "consents"] });

  return (
    <div className="rounded-md border border-[var(--campus-line)]">
      <div className="flex items-center justify-between border-b border-[var(--campus-line)] px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
          Consents
        </span>
        <span className="flex gap-2">
          <Button
            size="sm"
            variant="ghost"
            disabled={requesting}
            onClick={async () => {
              setRequesting(true);
              try {
                const res = await create<{ sent: boolean; to: string[] }>(
                  "consents/request", { student: studentId },
                );
                toast(
                  res.sent ? "success" : "error",
                  res.sent
                    ? `Requested from ${res.to.length} guardian(s)`
                    : "No communications-eligible guardian on file",
                );
              } catch (e) {
                toast("error", apiMessage(e));
              } finally {
                setRequesting(false);
              }
            }}
          >
            {requesting ? "Sending…" : "Request consent"}
          </Button>
          <Button size="sm" variant="subtle" onClick={() => setAdding(true)}>
            + Record
          </Button>
        </span>
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
                <span className="text-xs text-[var(--campus-muted)]">{date(r.recorded_at)}</span>
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
            await create("consents", { ...values, student: studentId, version: values.version || "1" });
            setAdding(false);
            reload();
          }}
          onCancel={() => setAdding(false)}
        />
      </Modal>
    </div>
  );
}
