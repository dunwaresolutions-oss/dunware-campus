"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAll, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { ActionButton } from "@/components/ActionButton";
import { ScheduleCalendar } from "@/components/ScheduleCalendar";
import { Modal } from "@/components/Modal";
import { PageHeader, Tabs, Badge, Spinner } from "@/components/ui";
import { date, time, weekday, label, apiMessage, yn, WEEKDAYS } from "@/lib/format";
import { act } from "@/lib/resource";
import { api } from "@/lib/api";
import { useToast } from "@/components/Toast";

interface Group {
  id: string;
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
interface SessionRow {
  id: number;
  group: string;
  group_name?: string;
  room_name?: string;
  date: string;
  start_time: string;
  end_time: string;
  title: string;
  status: string;
  cancelled_reason?: string;
}

const weekdayOptions = WEEKDAYS.map((w, i) => ({ value: i, label: w }));

export default function SchedulingPage() {
  const [tab, setTab] = useState("calendar");
  const [openSession, setOpenSession] = useState<SessionRow | null>(null);
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
        subtitle="The calendar of dated sessions (month / week / day), plus the rooms, academic year, recurring class templates and closures those sessions come from. Click a session for its roster."
      />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "calendar", label: "Calendar" },
          { key: "sessions", label: "Sessions" },
          { key: "templates", label: "Templates" },
          { key: "closures", label: "Closures" },
          { key: "terms", label: "Terms" },
          { key: "years", label: "Academic years" },
          { key: "rooms", label: "Rooms" },
        ]}
      />

      {tab === "calendar" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            Every dated session, in a month / week / day view. Filter by group,
            and click a session to see its roster or cancel that one meeting.
            Amber days are closures.
          </p>
          <ScheduleCalendar
            groups={groups.data ?? []}
            onOpenSession={(s) => setOpenSession(s as unknown as SessionRow)}
          />
        </>
      )}

      {tab === "rooms" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            A <b>room</b> is one physical space. Templates and booking offerings
            point at a room; Campus records it but does not hard-block a clash.
          </p>
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
            detailTitle={(r) => `Room — ${r.name}`}
            detailFields={[
              { label: "Name", value: (r) => r.name as string },
              { label: "Kind", value: (r) => label(r.kind as string) },
              { label: "Capacity", value: (r) => (r.capacity as number) ?? "—" },
              { label: "Active", value: (r) => yn(r.active) },
            ]}
          />
        </>
      )}

      {tab === "years" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            The <b>academic year</b> is the top of the calendar. Mark exactly one
            as current — registration, report cards and fee schedules read it.
            Terms live underneath.
          </p>
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
            detailTitle={(r) => `Academic year — ${r.name}`}
            detailFields={[
              { label: "Name", value: (r) => r.name as string },
              { label: "Starts", value: (r) => date(r.start_date as string) },
              { label: "Ends", value: (r) => date(r.end_date as string) },
              { label: "Current year", value: (r) => yn(r.is_current) },
            ]}
          />
        </>
      )}

      {tab === "terms" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            A <b>term</b> is a span inside the year. Pick the kind your school
            runs — semester / trimester / quarter / rolling / year-round. Session
            templates and report cards are scoped to a term.
          </p>
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
            detailTitle={(r) => `Term — ${r.name}`}
            detailFields={[
              { label: "Name", value: (r) => r.name as string },
              {
                label: "Academic year",
                value: (r) =>
                  years.data?.find((y) => y.id === r.academic_year)?.name ?? "—",
              },
              { label: "Kind", value: (r) => label(r.kind as string) },
              { label: "Starts", value: (r) => date(r.start_date as string) },
              { label: "Ends", value: (r) => date(r.end_date as string) },
            ]}
          />
        </>
      )}

      {tab === "closures" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            A <b>closure</b> is a day or span with no sessions. Leave the group
            blank for a site-wide closure (which also blocks booking-slot
            generation). Add closures <i>before</i> you generate.
          </p>
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
            detailTitle={() => "Closure"}
            detailFields={[
              { label: "From", value: (r) => date(r.start_date as string) },
              { label: "To", value: (r) => date(r.end_date as string) },
              {
                label: "Scope",
                value: (r) =>
                  r.group
                    ? (groups.data?.find((g) => g.id === r.group)?.name ??
                      "one group")
                    : "Site-wide",
              },
              { label: "Reason", value: (r) => (r.reason as string) || "—", long: true },
            ]}
          />
        </>
      )}

      {tab === "templates" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            A <b>template</b> is a recurring pattern — a group, a weekday, a
            start/end time, a room, a term. Press <b>Generate</b> with a date
            range to expand it into dated sessions; it skips closures and never
            duplicates, so re-run it whenever the term is extended.
          </p>
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
              { name: "title", label: "Title" },
            ]}
            detailTitle={(r) =>
              `Template — ${groups.data?.find((g) => g.id === r.group)?.name ?? "class"}`
            }
            detailFields={[
              {
                label: "Group",
                value: (r) =>
                  groups.data?.find((g) => g.id === r.group)?.name ?? String(r.group),
              },
              {
                label: "Term",
                value: (r) => terms.data?.find((t) => t.id === r.term)?.name ?? "—",
              },
              {
                label: "Room",
                value: (r) => rooms.data?.find((x) => x.id === r.room)?.name ?? "—",
              },
              { label: "Weekday", value: (r) => weekday(r.weekday as number) },
              {
                label: "Time",
                value: (r) =>
                  `${time(r.start_time as string)}–${time(r.end_time as string)}`,
              },
              { label: "Title", value: (r) => (r.title as string) || "—" },
              { label: "Active", value: (r) => yn(r.active) },
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
        </>
      )}

      {tab === "sessions" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            A <b>session</b> is one dated meeting of a group, generated from a
            template. Press <b>Open</b> to see its roster (the students actively
            enrolled in that group on that date) and to cancel the single
            meeting.
          </p>
          <CrudPanel<SessionRow>
            resource="sessions"
            singular="session"
            canCreate={false}
            canEdit={false}
            onRowOpen={setOpenSession}
            columns={[
              { header: "Date", cell: (r) => date(r.date) },
              {
                header: "Time",
                cell: (r) => `${time(r.start_time)}–${time(r.end_time)}`,
              },
              { header: "Group", cell: (r) => r.group_name ?? "—" },
              { header: "Room", cell: (r) => r.room_name ?? "—" },
              { header: "Title", cell: (r) => r.title || "—" },
              {
                header: "Status",
                cell: (r) => (
                  <Badge tone={r.status === "CANCELLED" ? "red" : "neutral"}>
                    {label(r.status)}
                  </Badge>
                ),
              },
            ]}
          />
        </>
      )}

      <SessionDrawer
        session={openSession}
        onClose={() => setOpenSession(null)}
      />
    </div>
  );
}

/* --------------------------------------------------------- session drawer */

interface RosterEntry {
  student_id: string;
  student_number: string;
  display_name: string;
}

function SessionDrawer({
  session,
  onClose,
}: {
  session: SessionRow | null;
  onClose: () => void;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [roster, setRoster] = useState<RosterEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string>(session?.status ?? "");

  useEffect(() => {
    setStatus(session?.status ?? "");
    if (!session) {
      setRoster(null);
      return;
    }
    setLoading(true);
    api<RosterEntry[]>(`/sessions/${session.id}/roster/`)
      .then((r) => setRoster(r ?? []))
      .catch((e) => {
        setRoster([]);
        toast("error", apiMessage(e));
      })
      .finally(() => setLoading(false));
  }, [session, toast]);

  if (!session) return null;

  const cancelled = status === "CANCELLED";

  return (
    <Modal
      open={!!session}
      onClose={onClose}
      title={`Session — ${session.title || session.group_name || "class"}`}
      wide
    >
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Badge tone={cancelled ? "red" : "neutral"}>{label(status)}</Badge>
          <span className="text-[var(--campus-muted)]">{date(session.date)}</span>
          <span className="text-[var(--campus-muted)]">
            {time(session.start_time)}–{time(session.end_time)}
          </span>
          <span className="text-[var(--campus-muted)]">{session.group_name ?? "—"}</span>
          <span className="text-[var(--campus-muted)]">{session.room_name ?? "no room"}</span>
        </div>
        {cancelled && session.cancelled_reason && (
          <p className="text-sm text-[var(--campus-muted)]">
            Cancelled: {session.cancelled_reason}
          </p>
        )}

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
            Roster{roster ? ` (${roster.length})` : ""}
          </h3>
          {loading ? (
            <Spinner />
          ) : !roster || roster.length === 0 ? (
            <p className="text-sm text-[var(--campus-muted)]">
              No students are actively enrolled in this group on this date.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--campus-line)] rounded-md border border-[var(--campus-line)] text-sm">
              {roster.map((s) => (
                <li key={s.student_id} className="flex justify-between px-3 py-2">
                  <span className="font-medium">{s.display_name}</span>
                  <span className="text-[var(--campus-muted)]">
                    {s.student_number}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {!cancelled && (
          <div className="flex justify-end border-t border-[var(--campus-line)] pt-3">
            <ActionButton
              label="Cancel this session"
              variant="ghost"
              title="Cancel this one meeting"
              fields={[{ name: "reason", label: "Reason" }]}
              onRun={(v) => act("sessions", session.id, "cancel", v)}
              onDone={() => {
                setStatus("CANCELLED");
                qc.invalidateQueries({ queryKey: ["list", "sessions"] });
                toast("success", "Session cancelled");
              }}
            />
          </div>
        )}
      </div>
    </Modal>
  );
}
