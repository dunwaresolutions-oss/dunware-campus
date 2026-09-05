"use client";

import { useState } from "react";
import { useAll, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { PageHeader, Tabs, Badge, Button } from "@/components/ui";
import { act } from "@/lib/resource";
import { useToast } from "@/components/Toast";
import { datetime, money, weekday, time, label, WEEKDAYS } from "@/lib/format";

export default function BookingPage() {
  const [tab, setTab] = useState("offerings");
  const toast = useToast();
  const offerings = useAll<{ id: number; title: string }>("offerings");
  const rooms = useAll<{ id: number; name: string }>("rooms");
  const students = useAll<{ id: string; display_name: string }>("students");
  const offeringOpts = options(offerings.data, (o) => o.title);
  const roomOpts = options(rooms.data, (r) => r.name);
  const studentOpts = options(students.data, (s) => s.display_name);
  const weekdayOpts = WEEKDAYS.map((w, i) => ({ value: i, label: w }));

  return (
    <div>
      <PageHeader
        title="Booking"
        subtitle="Tutoring and extra-curricular offerings, recurring availability, generated slots, and bookings (confirm-then-waitlist)."
      />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "offerings", label: "Offerings" },
          { key: "windows", label: "Availability" },
          { key: "slots", label: "Slots" },
          { key: "bookings", label: "Bookings" },
        ]}
      />

      {tab === "offerings" && (
        <CrudPanel
          resource="offerings"
          singular="offering"
          columns={[
            { header: "Title", cell: (r) => r.title as string },
            { header: "Kind", cell: (r) => label(r.kind as string) },
            {
              header: "Capacity/slot",
              cell: (r) => (r.capacity_per_slot as number) ?? "—",
            },
            { header: "Price", cell: (r) => money(r.price_cents as number) },
            {
              header: "Active",
              cell: (r) => (r.active ? <Badge tone="green">Yes</Badge> : "No"),
            },
          ]}
          fields={[
            { name: "title", label: "Title", required: true },
            {
              name: "kind",
              label: "Kind",
              type: "select",
              options: ["TUTORING", "MUSIC", "SPORT", "CLUB", "OTHER"].map(
                (v) => ({ value: v, label: label(v) }),
              ),
            },
            { name: "description", label: "Description", type: "textarea" },
            { name: "room", label: "Room", type: "select", options: roomOpts },
            { name: "duration_minutes", label: "Duration (min)", type: "number" },
            { name: "capacity_per_slot", label: "Capacity per slot", type: "number" },
            { name: "cancellation_hours", label: "Free-cancel cutoff (h)", type: "number" },
            { name: "price_cents", label: "Price", type: "money", help: "Placeholder — no charge in v1." },
            { name: "active", label: "Active", type: "checkbox" },
          ]}
          extraRowActions={(row, reload) => (
            <Button
              size="sm"
              variant="ghost"
              onClick={async () => {
                const from_date = window.prompt("Generate slots from (YYYY-MM-DD):");
                if (!from_date) return;
                const to_date = window.prompt("…through (YYYY-MM-DD):");
                if (!to_date) return;
                try {
                  await act("offerings", row.id as number, "generate_slots", {
                    from_date,
                    to_date,
                  });
                  toast("success", "Slots generated");
                  reload();
                } catch (e) {
                  toast("error", String((e as Error).message));
                }
              }}
            >
              Generate slots
            </Button>
          )}
        />
      )}

      {tab === "windows" && (
        <CrudPanel
          resource="availability-windows"
          singular="availability window"
          columns={[
            {
              header: "Offering",
              cell: (r) =>
                offerings.data?.find((o) => o.id === r.offering)?.title ??
                r.offering,
            },
            { header: "Weekday", cell: (r) => weekday(r.weekday as number) },
            {
              header: "Time",
              cell: (r) =>
                `${time(r.start_time as string)}–${time(r.end_time as string)}`,
            },
          ]}
          fields={[
            { name: "offering", label: "Offering", type: "select", required: true, options: offeringOpts },
            { name: "weekday", label: "Weekday", type: "select", required: true, options: weekdayOpts },
            { name: "start_time", label: "Start", type: "time", required: true },
            { name: "end_time", label: "End", type: "time", required: true },
            { name: "valid_from", label: "Valid from", type: "date" },
            { name: "valid_to", label: "Valid to", type: "date" },
            { name: "active", label: "Active", type: "checkbox" },
          ]}
        />
      )}

      {tab === "slots" && (
        <CrudPanel
          resource="slots"
          singular="slot"
          canCreate={false}
          columns={[
            {
              header: "Offering",
              cell: (r) => (r.offering_title as string) ?? r.offering,
            },
            { header: "Starts", cell: (r) => datetime(r.starts_at as string) },
            {
              header: "Seats left",
              cell: (r) => (r.seats_left as number) ?? "—",
            },
            {
              header: "Status",
              cell: (r) => <Badge>{label(r.status as string)}</Badge>,
            },
          ]}
          extraRowActions={(row, reload) =>
            row.status !== "CANCELLED" ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => {
                  if (!window.confirm("Cancel this slot and its bookings?"))
                    return;
                  try {
                    await act("slots", row.id as number, "cancel");
                    toast("success", "Slot cancelled");
                    reload();
                  } catch (e) {
                    toast("error", String((e as Error).message));
                  }
                }}
              >
                Cancel
              </Button>
            ) : null
          }
        />
      )}

      {tab === "bookings" && (
        <CrudPanel
          resource="bookings"
          singular="booking"
          columns={[
            {
              header: "Student",
              cell: (r) => (r.student_name as string) ?? r.student,
            },
            {
              header: "Offering",
              cell: (r) => (r.offering_title as string) ?? "—",
            },
            { header: "Starts", cell: (r) => datetime(r.starts_at as string) },
            {
              header: "Status",
              cell: (r) => (
                <Badge
                  tone={
                    r.status === "CONFIRMED"
                      ? "green"
                      : r.status === "WAITLISTED"
                        ? "amber"
                        : "neutral"
                  }
                >
                  {label(r.status as string)}
                  {r.status === "WAITLISTED" && r.waitlist_position
                    ? ` #${r.waitlist_position}`
                    : ""}
                </Badge>
              ),
            },
          ]}
          fields={[
            { name: "slot", label: "Slot id", type: "number", required: true },
            { name: "student", label: "Student", type: "select", required: true, options: studentOpts },
          ]}
          extraRowActions={(row, reload) =>
            row.status === "CONFIRMED" || row.status === "WAITLISTED" ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => {
                  try {
                    await act("bookings", row.id as number, "cancel");
                    toast("success", "Booking cancelled");
                    reload();
                  } catch (e) {
                    toast("error", String((e as Error).message));
                  }
                }}
              >
                Cancel
              </Button>
            ) : null
          }
        />
      )}
    </div>
  );
}
