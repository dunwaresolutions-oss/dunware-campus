"use client";

import { useState } from "react";
import { useAll, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { ActionButton } from "@/components/ActionButton";
import { PageHeader, Tabs, Badge } from "@/components/ui";
import { act } from "@/lib/resource";
import { date, label, today } from "@/lib/format";

interface Group {
  id: number;
  name: string;
}
interface Student {
  id: string;
  display_name: string;
}

export default function RegistrationPage() {
  const [tab, setTab] = useState("applications");
  const groups = useAll<Group>("groups");
  const students = useAll<Student>("students");
  const groupOpts = options(groups.data, (g) => g.name);
  const studentOpts = options(students.data, (s) => s.display_name);

  return (
    <div>
      <PageHeader
        title="Registration"
        subtitle="Applications through review, offers/waitlist, enrolment, and versioned consent."
      />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "applications", label: "Applications" },
          { key: "waitlist", label: "Waitlist" },
          { key: "offers", label: "Offers" },
          { key: "enrolments", label: "Enrolments" },
          { key: "consents", label: "Consents" },
        ]}
      />

      {tab === "applications" && (
        <CrudPanel
          resource="applications"
          singular="application"
          columns={[
            {
              header: "Child",
              cell: (r) =>
                `${(r.child_first_name as string) ?? ""} ${
                  (r.child_last_name as string) ?? ""
                }`.trim() || "—",
            },
            {
              header: "Applicant",
              cell: (r) => (r.applicant_name as string) || "—",
            },
            { header: "Submitted", cell: (r) => date(r.submitted_at as string) },
            {
              header: "Status",
              cell: (r) => <Badge>{label(r.status as string)}</Badge>,
            },
          ]}
          fields={[
            { name: "child_first_name", label: "Child first name", required: true },
            { name: "child_last_name", label: "Child last name", required: true },
            { name: "child_date_of_birth", label: "Child DOB", type: "date", required: true },
            { name: "desired_start", label: "Desired start", type: "date" },
            { name: "desired_group", label: "Desired group", type: "select", options: groupOpts },
            { name: "applicant_name", label: "Applicant name", required: true },
            { name: "applicant_email", label: "Applicant email", required: true },
            { name: "applicant_phone", label: "Applicant phone (encrypted)" },
            { name: "notes", label: "Notes (encrypted)", type: "textarea" },
          ]}
          extraRowActions={(row, reload) => {
            const id = row.id as string;
            const s = row.status as string;
            return (
              <>
                {s === "SUBMITTED" && (
                  <ActionButton
                    label="Review"
                    onRun={() => act("applications", id, "review")}
                    onDone={reload}
                  />
                )}
                {s !== "ENROLLED" && s !== "DECLINED" && (
                  <ActionButton
                    label="Make offer"
                    title="Make an offer"
                    fields={[
                      {
                        name: "group",
                        label: "Group",
                        type: "select",
                        required: true,
                        options: groupOpts,
                      },
                      { name: "start_date", label: "Start date", type: "date", required: true },
                      { name: "expires_at", label: "Offer expires", type: "date", required: true },
                    ]}
                    onRun={(v) => act("applications", id, "make_offer", v)}
                    onDone={reload}
                  />
                )}
                {s !== "ENROLLED" && (
                  <ActionButton
                    label="Convert"
                    title="Convert to an enrolled student"
                    fields={[
                      {
                        name: "group",
                        label: "Enrol into group",
                        type: "select",
                        options: groupOpts,
                        help: "Optional — leave blank to create the student without an enrolment.",
                      },
                      {
                        name: "start_date",
                        label: "Enrolment start",
                        type: "date",
                        help: "Defaults to today if a group is chosen.",
                      },
                    ]}
                    onRun={(v) =>
                      act("applications", id, "convert", {
                        group: v.group || undefined,
                        start_date: v.start_date || (v.group ? today() : undefined),
                      })
                    }
                    onDone={reload}
                  />
                )}
              </>
            );
          }}
        />
      )}

      {tab === "waitlist" && (
        <CrudPanel
          resource="waitlist"
          singular="waitlist entry"
          columns={[
            { header: "Child", cell: (r) => (r.child_name as string) || `#${r.application}` },
            {
              header: "Group",
              cell: (r) =>
                (r.group_name as string) ??
                groups.data?.find((g) => g.id === r.group)?.name ??
                r.group,
            },
            { header: "Priority", cell: (r) => (r.priority as number) ?? "—" },
            {
              header: "Active",
              cell: (r) => (r.active ? <Badge tone="green">Yes</Badge> : "No"),
            },
          ]}
          fields={[
            { name: "application", label: "Application id", type: "number", required: true },
            {
              name: "group",
              label: "Group",
              type: "select",
              required: true,
              options: groupOpts,
            },
            { name: "priority", label: "Priority", type: "number" },
            { name: "active", label: "Active", type: "checkbox" },
          ]}
        />
      )}

      {tab === "offers" && (
        <CrudPanel
          resource="offers"
          singular="offer"
          canCreate={false}
          columns={[
            { header: "Child", cell: (r) => (r.child_name as string) || `#${r.application}` },
            {
              header: "Group",
              cell: (r) =>
                (r.group_name as string) ??
                groups.data?.find((g) => g.id === r.group)?.name ??
                r.group,
            },
            { header: "Start", cell: (r) => date(r.start_date as string) },
            { header: "Expires", cell: (r) => date(r.expires_at as string) },
            {
              header: "Status",
              cell: (r) => <Badge>{label(r.status as string)}</Badge>,
            },
          ]}
          extraRowActions={(row, reload) => (
            <>
              <ActionButton
                label="Accept"
                onRun={() => act("offers", row.id as string, "accept")}
                onDone={reload}
              />
              <ActionButton
                label="Decline"
                variant="ghost"
                confirm="Decline this offer?"
                onRun={() => act("offers", row.id as string, "decline")}
                onDone={reload}
              />
            </>
          )}
        />
      )}

      {tab === "enrolments" && (
        <CrudPanel
          resource="enrolments"
          singular="enrolment"
          columns={[
            {
              header: "Student",
              cell: (r) =>
                (r.student_name as string) ||
                students.data?.find((s) => s.id === r.student)?.display_name ||
                (r.student as string),
            },
            {
              header: "Group",
              cell: (r) =>
                (r.group_name as string) ??
                groups.data?.find((g) => g.id === r.group)?.name ??
                r.group,
            },
            { header: "Start", cell: (r) => date(r.start_date as string) },
            { header: "End", cell: (r) => date(r.end_date as string) },
            {
              header: "Status",
              cell: (r) => (
                <Badge tone={r.status === "ACTIVE" ? "green" : "neutral"}>
                  {label(r.status as string)}
                </Badge>
              ),
            },
          ]}
          fields={[
            {
              name: "student",
              label: "Student",
              type: "select",
              required: true,
              options: studentOpts,
            },
            {
              name: "group",
              label: "Group",
              type: "select",
              required: true,
              options: groupOpts,
            },
            { name: "start_date", label: "Start date", type: "date", required: true },
          ]}
          extraRowActions={(row, reload) =>
            row.status === "ACTIVE" ? (
              <ActionButton
                label="End"
                title="End this enrolment"
                fields={[
                  {
                    name: "end_date",
                    label: "End date",
                    type: "date",
                    required: true,
                  },
                ]}
                onRun={(v) => act("enrolments", row.id as string, "end", v)}
                onDone={reload}
              />
            ) : null
          }
        />
      )}

      {tab === "consents" && (
        <CrudPanel
          resource="consents"
          singular="consent"
          columns={[
            {
              header: "Student",
              cell: (r) =>
                (r.student_name as string) ||
                students.data?.find((s) => s.id === r.student)?.display_name ||
                (r.student as string),
            },
            { header: "Kind", cell: (r) => label(r.kind as string) },
            { header: "Version", cell: (r) => (r.version as number) ?? 1 },
            {
              header: "Granted",
              cell: (r) =>
                r.granted ? (
                  <Badge tone="green">Granted</Badge>
                ) : (
                  <Badge tone="red">Withheld</Badge>
                ),
            },
          ]}
          fields={[
            {
              name: "student",
              label: "Student",
              type: "select",
              required: true,
              options: studentOpts,
            },
            {
              name: "kind",
              label: "Kind",
              type: "select",
              required: true,
              options: [
                "PHOTO",
                "MEDIA",
                "FIELD_TRIP",
                "DATA_SHARING",
                "MEDICAL_TREATMENT",
                "TECHNOLOGY",
                "SUNSCREEN",
              ].map((v) => ({ value: v, label: label(v) })),
            },
            { name: "granted", label: "Granted", type: "checkbox" },
          ]}
        />
      )}
    </div>
  );
}
