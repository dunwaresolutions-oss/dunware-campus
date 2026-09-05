"use client";

import { useState } from "react";
import { useAll, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { PageHeader, Tabs, Badge, Button } from "@/components/ui";
import { act } from "@/lib/resource";
import { useToast } from "@/components/Toast";
import { date, label } from "@/lib/format";

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
  const toast = useToast();
  const groups = useAll<Group>("groups");
  const students = useAll<Student>("students");
  const groupOpts = options(groups.data, (g) => g.name);
  const studentOpts = options(students.data, (s) => s.display_name);

  async function run(
    resource: string,
    id: number,
    verb: string,
    reload: () => void,
    body?: Record<string, unknown>,
  ) {
    try {
      await act(resource, id, verb, body);
      toast("success", `${label(verb)} done`);
      reload();
    } catch (e) {
      toast("error", String((e as Error).message));
    }
  }

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
            const id = row.id as number;
            const s = row.status as string;
            return (
              <>
                {s === "SUBMITTED" && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => run("applications", id, "review", reload)}
                  >
                    Review
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    const group = window.prompt(
                      "Offer for group id:\n" +
                        (groups.data ?? [])
                          .map((g) => `${g.id} = ${g.name}`)
                          .join("\n"),
                    );
                    if (!group) return;
                    const start_date = window.prompt("Start date (YYYY-MM-DD):");
                    if (!start_date) return;
                    const expires_at = window.prompt(
                      "Offer expires (YYYY-MM-DD):",
                    );
                    if (!expires_at) return;
                    run("applications", id, "make_offer", reload, {
                      group,
                      start_date,
                      expires_at,
                    });
                  }}
                >
                  Make offer
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    const group = window.prompt(
                      "Convert into group id (blank = none):",
                    );
                    run("applications", id, "convert", reload, {
                      group: group || undefined,
                    });
                  }}
                >
                  Convert
                </Button>
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
            { header: "Application", cell: (r) => `#${r.application}` },
            {
              header: "Group",
              cell: (r) =>
                groups.data?.find((g) => g.id === r.group)?.name ?? r.group,
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
            { header: "Application", cell: (r) => `#${r.application}` },
            {
              header: "Group",
              cell: (r) =>
                groups.data?.find((g) => g.id === r.group)?.name ?? r.group,
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
              <Button
                size="sm"
                variant="ghost"
                onClick={() => run("offers", row.id as number, "accept", reload)}
              >
                Accept
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => run("offers", row.id as number, "decline", reload)}
              >
                Decline
              </Button>
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
                students.data?.find((s) => s.id === r.student)?.display_name ??
                r.student,
            },
            {
              header: "Group",
              cell: (r) =>
                groups.data?.find((g) => g.id === r.group)?.name ?? r.group,
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
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  const end_date = window.prompt("End date (YYYY-MM-DD):");
                  if (end_date)
                    run("enrolments", row.id as number, "end", reload, {
                      end_date,
                    });
                }}
              >
                End
              </Button>
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
                students.data?.find((s) => s.id === r.student)?.display_name ??
                r.student,
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
