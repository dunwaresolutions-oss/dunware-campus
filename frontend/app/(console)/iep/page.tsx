"use client";

import { useState } from "react";
import { useQueryParam, useAll, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { NestedList } from "@/components/NestedList";
import { Modal } from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { PageHeader, Badge, Button, Spinner } from "@/components/ui";
import { date, label, apiMessage } from "@/lib/format";
import {
  iepDocument,
  IEP_STATUS,
  GOAL_AREAS,
  GOAL_PROGRESS,
  ACC_CATEGORIES,
  REVIEW_OUTCOMES,
  type IEP,
} from "@/lib/iep";

const statusTone = (s: string) =>
  s === "ACTIVE" ? "green" : s === "UNDER_REVIEW" ? "amber" : "neutral";

export default function IEPPage() {
  const toast = useToast();
  const focusStudent = useQueryParam("student");
  const [open, setOpen] = useState<IEP | null>(null);
  const students = useAll<{ id: string; display_name: string }>("students");
  const staff = useAll<{ id: string; display_name: string }>("auth/users");

  const studentOpts = options(students.data, (s) => s.display_name);
  const staffOpts = options(staff.data, (s) => s.display_name);
  const studentName = (id: string) =>
    students.data?.find((s) => s.id === id)?.display_name ?? id;

  const fields = [
    {
      name: "student",
      label: "Student",
      type: "select" as const,
      required: true,
      options: studentOpts,
    },
    { name: "school_year", label: "School year", placeholder: "2026–2027" },
    {
      name: "status",
      label: "Status",
      type: "select" as const,
      options: IEP_STATUS.map((v) => ({ value: v, label: label(v) })),
    },
    { name: "primary_concern", label: "Primary concern" },
    { name: "start_date", label: "Start date", type: "date" as const },
    { name: "review_date", label: "Next review", type: "date" as const },
    { name: "end_date", label: "End date", type: "date" as const },
    {
      name: "case_manager",
      label: "Case manager",
      type: "select" as const,
      options: staffOpts,
    },
    { name: "strengths", label: "Strengths (encrypted)", type: "textarea" as const },
    { name: "needs", label: "Needs (encrypted)", type: "textarea" as const },
    { name: "summary", label: "Summary (encrypted)", type: "textarea" as const },
  ];

  return (
    <div>
      <PageHeader
        title="IEPs"
        subtitle="Individual Education Plans — goals, accommodations, services and review history for a student. Content is encrypted at rest; every read is audited. Guardians see active plans on the portal."
      />
      <CrudPanel<IEP>
        resource="ieps"
        singular="IEP"
        query={focusStudent ? { student: focusStudent } : undefined}
        fields={fields}
        onRowOpen={setOpen}
        columns={[
          { header: "Student", cell: (r) => r.student_name || studentName(r.student) },
          { header: "Concern", cell: (r) => r.primary_concern || "—" },
          { header: "Year", cell: (r) => r.school_year || "—" },
          { header: "Goals", cell: (r) => r.goal_count ?? 0 },
          { header: "Review", cell: (r) => date(r.review_date) },
          {
            header: "Status",
            cell: (r) => <Badge tone={statusTone(r.status)}>{label(r.status)}</Badge>,
          },
        ]}
      />
      <IEPDrawer
        iep={open}
        onClose={() => setOpen(null)}
        studentName={open ? studentName(open.student) : ""}
        onErr={(e) => toast("error", apiMessage(e))}
      />
    </div>
  );
}

function IEPDrawer({
  iep,
  onClose,
  studentName,
  onErr,
}: {
  iep: IEP | null;
  onClose: () => void;
  studentName: string;
  onErr: (e: unknown) => void;
}) {
  const [docHtml, setDocHtml] = useState<string | null>(null);
  const [loadingDoc, setLoadingDoc] = useState(false);

  if (!iep) return null;

  async function openDoc() {
    setLoadingDoc(true);
    try {
      setDocHtml((await iepDocument(iep!.id)).html);
    } catch (e) {
      onErr(e);
    } finally {
      setLoadingDoc(false);
    }
  }

  return (
    <Modal open={!!iep} onClose={onClose} title={`IEP — ${studentName}`} wide>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Badge tone={statusTone(iep.status)}>{label(iep.status)}</Badge>
          {iep.school_year && <span className="text-[var(--campus-muted)]">{iep.school_year}</span>}
          {iep.primary_concern && (
            <span className="text-[var(--campus-muted)]">{iep.primary_concern}</span>
          )}
          {iep.review_date && (
            <span className="text-[var(--campus-muted)]">review {date(iep.review_date)}</span>
          )}
          {iep.case_manager_name && (
            <span className="text-[var(--campus-muted)]">case mgr: {iep.case_manager_name}</span>
          )}
          <Button size="sm" variant="ghost" className="ml-auto" disabled={loadingDoc} onClick={openDoc}>
            {loadingDoc ? "…" : "View document"}
          </Button>
        </div>

        {(["strengths", "needs", "summary"] as const).map((k) =>
          iep[k] ? (
            <section key={k}>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
                {label(k)}
              </h3>
              <p className="whitespace-pre-wrap text-sm">{iep[k]}</p>
            </section>
          ) : null,
        )}

        <NestedList
          resource="iep-goals"
          parentKey="iep"
          parentId={iep.id}
          title="Goals"
          render={(r) => (
            <span>
              <span className="font-medium">{label(r.area as string)}</span> —{" "}
              {r.description as string}
              <span className="text-[var(--campus-muted)]"> · {label(r.progress as string)}</span>
            </span>
          )}
          addFields={[
            {
              name: "area",
              label: "Area",
              type: "select",
              required: true,
              options: GOAL_AREAS.map((v) => ({ value: v, label: label(v) })),
            },
            { name: "description", label: "Goal (encrypted)", type: "textarea", required: true },
            { name: "baseline", label: "Baseline (encrypted)", type: "textarea" },
            { name: "target", label: "Target (encrypted)", type: "textarea" },
            {
              name: "progress",
              label: "Progress",
              type: "select",
              options: GOAL_PROGRESS.map((v) => ({ value: v, label: label(v) })),
            },
            { name: "progress_notes", label: "Progress notes (encrypted)", type: "textarea" },
            { name: "order", label: "Order", type: "number" },
          ]}
        />

        <NestedList
          resource="iep-accommodations"
          parentKey="iep"
          parentId={iep.id}
          title="Accommodations"
          render={(r) => (
            <span>
              <span className="font-medium">{label(r.category as string)}</span> —{" "}
              {r.description as string}
              <span className="text-[var(--campus-muted)]"> ({r.applies_to as string})</span>
              {r.active ? "" : " · inactive"}
            </span>
          )}
          addFields={[
            {
              name: "category",
              label: "Category",
              type: "select",
              required: true,
              options: ACC_CATEGORIES.map((v) => ({ value: v, label: label(v) })),
            },
            { name: "description", label: "Description (encrypted)", type: "textarea", required: true },
            { name: "applies_to", label: "Applies to", placeholder: "All classes" },
            { name: "active", label: "Active", type: "checkbox" },
          ]}
        />

        <NestedList
          resource="iep-services"
          parentKey="iep"
          parentId={iep.id}
          title="Services"
          render={(r) => (
            <span>
              <span className="font-medium">{r.service as string}</span>
              {r.provider ? ` · ${r.provider as string}` : ""}
              {r.frequency ? ` · ${r.frequency as string}` : ""}
              {r.location ? ` · ${r.location as string}` : ""}
            </span>
          )}
          addFields={[
            { name: "service", label: "Service", required: true },
            { name: "provider", label: "Provider" },
            { name: "frequency", label: "Frequency", placeholder: "2 × 30 min / week" },
            { name: "location", label: "Location" },
            { name: "start_date", label: "Starts", type: "date" },
            { name: "end_date", label: "Ends", type: "date" },
            { name: "notes", label: "Notes (encrypted)", type: "textarea" },
          ]}
        />

        <NestedList
          resource="iep-reviews"
          parentKey="iep"
          parentId={iep.id}
          title="Review history"
          render={(r) => (
            <span>
              <span className="text-[var(--campus-muted)]">{date(r.review_date as string)}</span> ·{" "}
              {label(r.outcome as string)}
              {r.notes ? ` — ${r.notes as string}` : ""}
            </span>
          )}
          addFields={[
            { name: "review_date", label: "Review date", type: "date", required: true },
            { name: "attendees", label: "Attendees" },
            {
              name: "outcome",
              label: "Outcome",
              type: "select",
              required: true,
              options: REVIEW_OUTCOMES.map((v) => ({ value: v, label: label(v) })),
            },
            { name: "notes", label: "Notes (encrypted)", type: "textarea" },
            { name: "next_review_date", label: "Next review", type: "date" },
          ]}
        />
      </div>

      <Modal open={docHtml != null} onClose={() => setDocHtml(null)} title="IEP document" wide>
        {docHtml == null ? (
          <Spinner />
        ) : (
          <iframe
            title="IEP"
            srcDoc={docHtml}
            className="h-[70vh] w-full rounded-lg border border-[var(--campus-line)] bg-white"
          />
        )}
      </Modal>
    </Modal>
  );
}
