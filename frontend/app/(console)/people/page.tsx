"use client";

import { useState } from "react";
import { useAll, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { NestedList } from "@/components/NestedList";
import { PageHeader, Tabs, Badge, Button } from "@/components/ui";
import { Modal } from "@/components/Modal";
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
  const groups = useAll<Group>("groups");
  const groupOpts = options(groups.data, (g) => g.name);
  const guardiansAll = useAll<{
    id: number;
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
            { header: "Email", cell: (g) => (g.email as string) || "—" },
            { header: "Phone", cell: (g) => (g.phone as string) || "—" },
          ]}
          fields={[
            { name: "first_name", label: "First name", required: true },
            { name: "last_name", label: "Last name", required: true },
            { name: "email", label: "Email" },
            { name: "phone", label: "Phone (encrypted)" },
            { name: "address", label: "Address (encrypted)", type: "textarea" },
          ]}
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
              <div className="text-neutral-500">Date of birth</div>
              <div>{date(detail.date_of_birth)}</div>
              <div className="text-neutral-500">Status</div>
              <div>{label(detail.status)}</div>
              <div className="text-neutral-500">Group</div>
              <div>{detail.primary_group_name || "—"}</div>
              <div className="text-neutral-500">Pronouns</div>
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
                  <span className="text-neutral-500">
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
                  <span className="text-neutral-500">
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
              render={(r) => <span>{r.name as string}</span>}
            />
            <NestedList
              resource="health/allergies"
              parentKey="student"
              parentId={detail.id}
              title="Health — allergies"
              render={(r) => (
                <span>
                  {r.allergen as string} —{" "}
                  <span className="text-neutral-500">
                    {label(r.severity as string)}
                  </span>
                </span>
              )}
            />

            <NestedList
              resource="documents"
              parentKey="student"
              parentId={detail.id}
              title="Documents"
              render={(r) => (
                <a
                  href={(r.download_url as string) || "#"}
                  className="text-sky-700 hover:underline"
                >
                  {r.title as string} ({label(r.kind as string)})
                </a>
              )}
            />
          </div>
        )}
      </Modal>
    </div>
  );
}
