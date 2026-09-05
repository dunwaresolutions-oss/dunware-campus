"use client";

import { useState } from "react";
import { useAll, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { ActionButton } from "@/components/ActionButton";
import { PageHeader, Tabs, Badge, Button } from "@/components/ui";
import { date, time, weekday, label, WEEKDAYS } from "@/lib/format";
import { act } from "@/lib/resource";
import { api } from "@/lib/api";
import { useToast } from "@/components/Toast";

interface Group {
  id: number;
  name: string;
}
interface Term {
  id: number;
  name: string;
}
interface Room {
  id: number;
  name: string;
}

const weekdayOptions = WEEKDAYS.map((w, i) => ({ value: i, label: w }));

export default function SchedulingPage() {
  const [tab, setTab] = useState("sessions");
  const toast = useToast();
  const groups = useAll<Group>("groups");
  const terms = useAll<Term>("terms");
  const rooms = useAll<Room>("rooms");
  const years = useAll<{ id: number; name: string }>("academic-years");

  const groupOpts = options(groups.data, (g) => g.name);
  const termOpts = options(terms.data, (t) => t.name);
  const roomOpts = options(rooms.data, (r) => r.name);
  const yearOpts = options(years.data, (y) => y.name);

  return (
    <div>
      <PageHeader
        title="Scheduling"
        subtitle="Rooms, the academic calendar, recurring class templates, and the dated sessions they expand into."
      />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "sessions", label: "Sessions" },
          { key: "templates", label: "Templates" },
          { key: "closures", label: "Closures" },
          { key: "terms", label: "Terms" },
          { key: "years", label: "Academic years" },
          { key: "rooms", label: "Rooms" },
        ]}
      />

      {tab === "rooms" && (
        <CrudPanel
          resource="rooms"
          singular="room"
          columns={[
            { header: "Name", cell: (r) => r.name as string },
            { header: "Kind", cell: (r) => label(r.kind as string) },
            { header: "Capacity", cell: (r) => (r.capacity as number) ?? "—" },
            {
              header: "Active",
              cell: (r) => (r.active ? <Badge tone="green">Yes</Badge> : "No"),
            },
          ]}
          fields={[
            { name: "name", label: "Name", required: true },
            {
              name: "kind",
              label: "Kind",
              type: "select",
              options: ["CLASSROOM", "GYM", "OUTDOOR", "RESOURCE"].map((v) => ({
                value: v,
                label: label(v),
              })),
            },
            { name: "capacity", label: "Capacity", type: "number" },
            { name: "active", label: "Active", type: "checkbox" },
          ]}
        />
      )}

      {tab === "years" && (
        <CrudPanel
          resource="academic-years"
          singular="academic year"
          columns={[
            { header: "Name", cell: (r) => r.name as string },
            { header: "Start", cell: (r) => date(r.start_date as string) },
            { header: "End", cell: (r) => date(r.end_date as string) },
            {
              header: "Current",
              cell: (r) =>
                r.is_current ? <Badge tone="sky">Current</Badge> : "—",
            },
          ]}
          fields={[
            { name: "name", label: "Name", required: true, placeholder: "2026–2027" },
            { name: "start_date", label: "Start date", type: "date", required: true },
            { name: "end_date", label: "End date", type: "date", required: true },
            { name: "is_current", label: "Current year", type: "checkbox" },
          ]}
        />
      )}

      {tab === "terms" && (
        <CrudPanel
          resource="terms"
          singular="term"
          columns={[
            { header: "Name", cell: (r) => r.name as string },
            { header: "Kind", cell: (r) => label(r.kind as string) },
            { header: "Start", cell: (r) => date(r.start_date as string) },
            { header: "End", cell: (r) => date(r.end_date as string) },
          ]}
          fields={[
            {
              name: "academic_year",
              label: "Academic year",
              type: "select",
              required: true,
              options: yearOpts,
            },
            { name: "name", label: "Name", required: true },
            {
              name: "kind",
              label: "Kind",
              type: "select",
              options: [
                "SEMESTER",
                "TRIMESTER",
                "QUARTER",
                "ROLLING",
                "YEAR_ROUND",
              ].map((v) => ({ value: v, label: label(v) })),
            },
            { name: "start_date", label: "Start date", type: "date", required: true },
            { name: "end_date", label: "End date", type: "date", required: true },
          ]}
        />
      )}

      {tab === "closures" && (
        <CrudPanel
          resource="closures"
          singular="closure"
          columns={[
            { header: "From", cell: (r) => date(r.start_date as string) },
            { header: "To", cell: (r) => date(r.end_date as string) },
            { header: "Reason", cell: (r) => (r.reason as string) || "—" },
            {
              header: "Scope",
              cell: (r) => (r.group ? "Group" : "Site-wide"),
            },
          ]}
          fields={[
            { name: "start_date", label: "From", type: "date", required: true },
            { name: "end_date", label: "To", type: "date", required: true },
            { name: "reason", label: "Reason" },
            {
              name: "group",
              label: "Group (blank = whole site)",
              type: "select",
              options: groupOpts,
            },
          ]}
        />
      )}

      {tab === "templates" && (
        <CrudPanel
          resource="session-templates"
          singular="template"
          columns={[
            {
              header: "Group",
              cell: (r) =>
                groups.data?.find((g) => g.id === r.group)?.name ?? r.group,
            },
            { header: "Weekday", cell: (r) => weekday(r.weekday as number) },
            {
              header: "Time",
              cell: (r) =>
                `${time(r.start_time as string)}–${time(r.end_time as string)}`,
            },
            {
              header: "Room",
              cell: (r) =>
                rooms.data?.find((x) => x.id === r.room)?.name ?? "—",
            },
          ]}
          fields={[
            {
              name: "group",
              label: "Group",
              type: "select",
              required: true,
              options: groupOpts,
            },
            {
              name: "term",
              label: "Term",
              type: "select",
              required: true,
              options: termOpts,
            },
            { name: "room", label: "Room", type: "select", options: roomOpts },
            {
              name: "weekday",
              label: "Weekday",
              type: "select",
              required: true,
              options: weekdayOptions,
            },
            { name: "start_time", label: "Start", type: "time", required: true },
            { name: "end_time", label: "End", type: "time", required: true },
          ]}
          extraRowActions={(row, reload) => (
            <ActionButton
              label="Generate"
              title="Generate dated sessions from this template"
              fields={[
                { name: "from_date", label: "From", type: "date", required: true },
                { name: "to_date", label: "Through", type: "date", required: true },
              ]}
              onRun={(v) => act("session-templates", row.id as string, "generate", v)}
              onDone={reload}
            />
          )}
        />
      )}

      {tab === "sessions" && (
        <CrudPanel
          resource="sessions"
          singular="session"
          canCreate={false}
          columns={[
            {
              header: "Date",
              cell: (r) => date(r.starts_at as string),
            },
            { header: "Time", cell: (r) => time(r.starts_at as string) },
            { header: "Group", cell: (r) => (r.group_name as string) ?? "—" },
            { header: "Room", cell: (r) => (r.room_name as string) ?? "—" },
            {
              header: "Status",
              cell: (r) => <Badge>{label(r.status as string)}</Badge>,
            },
          ]}
          extraRowActions={(row) => (
            <Button
              size="sm"
              variant="ghost"
              onClick={async () => {
                try {
                  const roster = await api<
                    Array<{ student_name?: string; display_name?: string }>
                  >(`/sessions/${row.id}/roster/`);
                  const names = (roster ?? [])
                    .map((r) => r.student_name ?? r.display_name)
                    .filter(Boolean);
                  toast(
                    "info",
                    names.length
                      ? `${names.length}: ${names.slice(0, 6).join(", ")}${names.length > 6 ? "…" : ""}`
                      : "No students on this roster",
                  );
                } catch (e) {
                  toast("error", String((e as Error).message));
                }
              }}
            >
              Roster
            </Button>
          )}
        />
      )}
    </div>
  );
}
