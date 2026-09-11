"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAll, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { ActionButton } from "@/components/ActionButton";
import { Modal } from "@/components/Modal";
import { PageHeader, Tabs, Badge, Button, Spinner } from "@/components/ui";
import { act, patch, retrieve } from "@/lib/resource";
import { useToast } from "@/components/Toast";
import { datetime, date, money, time, label, apiMessage, yn, WEEKDAYS } from "@/lib/format";
import { searchStudents } from "@/lib/students";

interface OfferingRow {
  id: number;
  title: string;
  kind: string;
  description: string;
  provider: number | null;
  room: number | null;
  duration_minutes: number;
  capacity_per_slot: number;
  cancellation_hours: number;
  price_cents: number | null;
  active: boolean;
}

export default function BookingPage() {
  const [tab, setTab] = useState("offerings");
  const [openOffering, setOpenOffering] = useState<OfferingRow | null>(null);
  const toast = useToast();
  const offerings = useAll<{ id: number; title: string }>("offerings");
  const rooms = useAll<{ id: number; name: string }>("rooms");
  const offeringOpts = options(offerings.data, (o) => o.title);
  const roomOpts = options(rooms.data, (r) => r.name);
  const weekdayOpts = WEEKDAYS.map((w, i) => ({ value: i, label: w }));
  const roomName = (id: number | null) =>
    id == null ? "—" : (rooms.data?.find((r) => r.id === id)?.name ?? String(id));

  return (
    <div>
      <PageHeader
        title="Booking"
        subtitle="Tutoring and extra-curricular offerings, their recurring availability, the dated capacity-limited slots that availability expands into, and bookings — which confirm while seats last, then waitlist in order. Press Open on an offering to see it whole."
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
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            An <b>offering</b> is a bookable activity — a tutor&apos;s time, a
            music lesson, a sport, a club. It sets the <b>capacity per slot</b>,
            the session length, and the <b>free-cancellation cutoff</b>. The price
            field is a placeholder; no money moves through booking in this
            version. Press <b>Open</b> to read the description and see its
            availability, generated slots and bookings together.
          </p>
          <CrudPanel<OfferingRow>
            resource="offerings"
            singular="offering"
            onRowOpen={setOpenOffering}
            columns={[
              { header: "Title", cell: (r) => r.title },
              { header: "Kind", cell: (r) => label(r.kind) },
              { header: "Capacity/slot", cell: (r) => r.capacity_per_slot ?? "—" },
              { header: "Length", cell: (r) => `${r.duration_minutes} min` },
              { header: "Price", cell: (r) => money(r.price_cents) },
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
              <ActionButton
                label="Generate slots"
                title="Generate bookable slots for this offering"
                fields={[
                  { name: "from_date", label: "From", type: "date", required: true },
                  { name: "to_date", label: "Through", type: "date", required: true },
                ]}
                onRun={(v) => act("offerings", row.id, "generate_slots", v)}
                onDone={reload}
              />
            )}
          />
        </>
      )}

      {tab === "windows" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            An <b>availability window</b> is a recurring weekly time an offering
            could run, within a valid-from/to range. Windows describe when it{" "}
            <i>could</i> run; they create nothing bookable until you generate
            slots from the offering.
          </p>
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
              { header: "Weekday", cell: (r) => WEEKDAYS[r.weekday as number] ?? "—" },
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
            detailTitle={() => "Availability window"}
            detailFields={[
              {
                label: "Offering",
                value: (r) =>
                  offerings.data?.find((o) => o.id === r.offering)?.title ??
                  String(r.offering),
              },
              { label: "Weekday", value: (r) => WEEKDAYS[r.weekday as number] ?? "—" },
              {
                label: "Time",
                value: (r) =>
                  `${time(r.start_time as string)}–${time(r.end_time as string)}`,
              },
              { label: "Valid from", value: (r) => date(r.valid_from as string) },
              { label: "Valid to", value: (r) => date(r.valid_to as string) },
              { label: "Active", value: (r) => yn(r.active) },
            ]}
          />
        </>
      )}

      {tab === "slots" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            A <b>slot</b> is one concrete dated opening with a seat count.{" "}
            <b>Cancel</b> pulls a slot <i>and every booking on it</i> — confirmed
            and waitlisted — with no promotion.
          </p>
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
            detailTitle={(r) => `Slot — ${(r.offering_title as string) ?? "activity"}`}
            detailFields={[
              {
                label: "Offering",
                value: (r) => (r.offering_title as string) ?? String(r.offering),
              },
              { label: "Starts", value: (r) => datetime(r.starts_at as string) },
              { label: "Ends", value: (r) => datetime(r.ends_at as string) },
              { label: "Capacity", value: (r) => (r.capacity as number) ?? "—" },
              { label: "Confirmed", value: (r) => (r.confirmed_count as number) ?? 0 },
              { label: "Seats left", value: (r) => (r.seats_left as number) ?? 0 },
              { label: "Status", value: (r) => label(r.status as string) },
            ]}
            extraRowActions={(row, reload) =>
              row.status !== "CANCELLED" ? (
                <ActionButton
                  label="Cancel"
                  variant="ghost"
                  confirm="Cancel this slot and every booking on it?"
                  onRun={() => act("slots", row.id as number, "cancel")}
                  onDone={reload}
                />
              ) : null
            }
          />
        </>
      )}

      {tab === "bookings" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            A <b>booking</b> puts one student in one slot. It is <b>Confirmed</b>{" "}
            while the slot has a seat, otherwise <b>Waitlisted #N</b>. Cancelling a
            confirmed booking auto-promotes the first waitlisted one (silently —
            an audit entry, no email).
          </p>
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
              {
                name: "student", label: "Student", type: "search-select", required: true,
                search: searchStudents, initialLabelKey: "student_name",
              },
            ]}
            detailTitle={(r) => `Booking — ${(r.student_name as string) ?? "student"}`}
            detailFields={[
              {
                label: "Student",
                value: (r) => (r.student_name as string) ?? String(r.student),
              },
              {
                label: "Offering",
                value: (r) => (r.offering_title as string) ?? "—",
              },
              { label: "Slot starts", value: (r) => datetime(r.starts_at as string) },
              {
                label: "Status",
                value: (r) =>
                  `${label(r.status as string)}${
                    r.status === "WAITLISTED" && r.waitlist_position
                      ? ` (#${r.waitlist_position})`
                      : ""
                  }`,
              },
              { label: "Booked", value: (r) => date(r.created_at as string) },
              {
                label: "Cancelled",
                value: (r) =>
                  r.cancelled_at ? datetime(r.cancelled_at as string) : "—",
              },
              {
                label: "Cancellation note",
                value: (r) => (r.cancellation_note as string) || "—",
                long: true,
              },
            ]}
            extraRowActions={(row, reload) =>
              row.status === "CONFIRMED" || row.status === "WAITLISTED" ? (
                <ActionButton
                  label="Cancel"
                  variant="ghost"
                  onRun={() => act("bookings", row.id as number, "cancel")}
                  onDone={reload}
                />
              ) : null
            }
          />
        </>
      )}

      <OfferingDrawer
        offering={openOffering}
        onClose={() => setOpenOffering(null)}
        roomName={roomName(openOffering?.room ?? null)}
        onToast={toast}
      />
    </div>
  );
}

/* ------------------------------------------------------- offering drawer */

interface WindowRow {
  id: number;
  offering: number;
  weekday: number;
  start_time: string;
  end_time: string;
  valid_from: string | null;
  valid_to: string | null;
  active: boolean;
}
interface SlotRow {
  id: number;
  offering: number;
  starts_at: string;
  seats_left: number;
  confirmed_count: number;
  capacity: number;
  status: string;
}

function OfferingDrawer({
  offering,
  onClose,
  roomName,
  onToast,
}: {
  offering: OfferingRow | null;
  onClose: () => void;
  roomName: string;
  onToast: (kind: "success" | "error" | "info", msg: string) => void;
}) {
  const qc = useQueryClient();
  const [live, setLive] = useState<OfferingRow | null>(offering);
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const windows = useAll<WindowRow>("availability-windows");
  const slots = useAll<SlotRow>(
    "slots",
    offering ? { offering: offering.id } : undefined,
    !!offering,
  );

  useEffect(() => {
    setLive(offering);
    setDescription(offering?.description ?? "");
  }, [offering]);

  if (!offering || !live) return null;

  const mineWindows = (windows.data ?? []).filter(
    (w) => w.offering === offering.id,
  );
  const mineSlots = (slots.data ?? [])
    .slice()
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  const upcoming = mineSlots.filter(
    (s) => new Date(s.starts_at).getTime() > Date.now(),
  );

  async function refresh() {
    if (!offering) return;
    const fresh = await retrieve<OfferingRow>("offerings", offering.id);
    setLive(fresh);
    setDescription(fresh.description ?? "");
    qc.invalidateQueries({ queryKey: ["list", "offerings"] });
    qc.invalidateQueries({ queryKey: ["all", "slots", { offering: offering.id }] });
  }

  async function withBusy(key: string, fn: () => Promise<void>) {
    setBusy(key);
    try {
      await fn();
    } catch (e) {
      onToast("error", apiMessage(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Modal open={!!offering} onClose={onClose} title={`Offering — ${live.title}`} wide>
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Badge tone={live.active ? "green" : "neutral"}>
            {live.active ? "Active" : "Inactive"}
          </Badge>
          <span className="text-[var(--campus-muted)]">{label(live.kind)}</span>
          <span className="text-[var(--campus-muted)]">{roomName}</span>
          <span className="text-[var(--campus-muted)]">
            {live.duration_minutes} min · capacity {live.capacity_per_slot}/slot
          </span>
          <span className="text-[var(--campus-muted)]">
            free-cancel cutoff {live.cancellation_hours} h
          </span>
          <span className="text-[var(--campus-muted)]">
            price {money(live.price_cents)} (placeholder)
          </span>
        </div>

        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
            Description
          </h3>
          <textarea
            className="w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm text-[var(--campus-fg)]"
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <div className="mt-1 flex justify-end">
            <Button
              size="sm"
              variant="subtle"
              disabled={busy === "desc" || description === (live.description ?? "")}
              onClick={() =>
                withBusy("desc", async () => {
                  await patch("offerings", offering.id, { description });
                  onToast("success", "Saved");
                  await refresh();
                })
              }
            >
              {busy === "desc" ? "Saving…" : "Save description"}
            </Button>
          </div>
        </section>

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
            Availability windows ({mineWindows.length})
          </h3>
          {mineWindows.length === 0 ? (
            <p className="text-sm text-[var(--campus-muted)]">
              None. Add one on the <b>Availability</b> tab, then generate slots.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--campus-line)] rounded-md border border-[var(--campus-line)] text-sm">
              {mineWindows.map((w) => (
                <li key={w.id} className="flex justify-between px-3 py-2">
                  <span>
                    {WEEKDAYS[w.weekday] ?? "?"} {time(w.start_time)}–
                    {time(w.end_time)}
                  </span>
                  <span className="text-[var(--campus-muted)]">
                    {w.valid_from ? date(w.valid_from) : "—"} →{" "}
                    {w.valid_to ? date(w.valid_to) : "—"}
                    {w.active ? "" : " · inactive"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
              Slots — {mineSlots.length} total, {upcoming.length} upcoming
            </h3>
            <ActionButton
              label="Generate slots"
              title="Generate bookable slots for this offering"
              fields={[
                { name: "from_date", label: "From", type: "date", required: true },
                { name: "to_date", label: "Through", type: "date", required: true },
              ]}
              onRun={(v) => act("offerings", offering.id, "generate_slots", v)}
              onDone={refresh}
            />
          </div>
          {slots.isLoading ? (
            <Spinner />
          ) : upcoming.length === 0 ? (
            <p className="text-sm text-[var(--campus-muted)]">
              No upcoming slots. Use <b>Generate slots</b> above with a date
              range.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--campus-line)] rounded-md border border-[var(--campus-line)] text-sm">
              {upcoming.slice(0, 12).map((s) => (
                <li key={s.id} className="flex items-center justify-between px-3 py-2">
                  <span>{datetime(s.starts_at)}</span>
                  <span className="flex items-center gap-2">
                    <span className="text-[var(--campus-muted)]">
                      {s.confirmed_count}/{s.capacity} · {s.seats_left} left
                    </span>
                    <Badge tone={s.status === "OPEN" ? "green" : "neutral"}>
                      {label(s.status)}
                    </Badge>
                  </span>
                </li>
              ))}
              {upcoming.length > 12 && (
                <li className="px-3 py-2 text-xs text-[var(--campus-muted)]">
                  …and {upcoming.length - 12} more. Full list on the{" "}
                  <b>Slots</b> tab.
                </li>
              )}
            </ul>
          )}
        </section>
      </div>
    </Modal>
  );
}
