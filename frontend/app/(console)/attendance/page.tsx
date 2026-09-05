"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useAll, useList } from "@/lib/hooks";
import { actList, act } from "@/lib/resource";
import { apiMessage, today, time, label } from "@/lib/format";
import {
  PageHeader,
  Card,
  Spinner,
  Badge,
  Button,
  EmptyState,
} from "@/components/ui";
import { Modal } from "@/components/Modal";
import { useToast } from "@/components/Toast";

interface Group {
  id: number;
  name: string;
}
interface Student {
  id: string;
  display_name: string;
  primary_group: number | null;
}
interface Rec {
  id: string;
  student: string;
  status: string;
  checked_in_at: string | null;
  checked_out_at: string | null;
  is_checked_in: boolean;
}
interface Pickup {
  id: string;
  student: string;
  name: string;
}
interface Link {
  id: string;
  student: string;
  guardian_name?: string;
  can_pickup?: boolean;
}

export default function AttendancePage() {
  const qc = useQueryClient();
  const toast = useToast();
  const [group, setGroup] = useState("");
  const [day, setDay] = useState(today());
  const [checkout, setCheckout] = useState<{ rec: Rec; student: Student } | null>(
    null,
  );

  const groups = useAll<Group>("groups");
  const students = useAll<Student>("students");
  const pickups = useAll<Pickup>("authorized-pickups");
  const links = useAll<Link>("guardian-links");
  const records = useList<Rec>(
    "attendance",
    { group, date: day },
    Boolean(group),
  );

  const reload = () =>
    qc.invalidateQueries({ queryKey: ["list", "attendance"] });

  const roster = (students.data ?? []).filter(
    (s) => String(s.primary_group) === group,
  );
  const recFor = (sid: string) =>
    (records.data?.results ?? []).find((r) => r.student === sid);

  async function checkIn(s: Student) {
    try {
      await actList("attendance", "check-in", {
        student: s.id,
        group,
        date: day,
      });
      toast("success", `${s.display_name} checked in`);
      reload();
    } catch (e) {
      toast("error", apiMessage(e));
    }
  }
  async function absent(s: Student) {
    try {
      await actList("attendance", "mark-absent", {
        student: s.id,
        group,
        date: day,
      });
      toast("success", `${s.display_name} marked absent`);
      reload();
    } catch (e) {
      toast("error", apiMessage(e));
    }
  }
  async function doCheckout(recId: string, body: Record<string, string>) {
    try {
      await act("attendance", recId, "check-out", body);
      toast("success", "Checked out");
      setCheckout(null);
      reload();
    } catch (e) {
      toast("error", apiMessage(e));
    }
  }

  return (
    <div>
      <PageHeader
        title="Attendance"
        subtitle="Pick a group and date, then check children in and out — check-out is only allowed to an authorized pickup or a guardian cleared for pickup."
      />

      <div className="mb-5 flex flex-wrap gap-3">
        <select
          className="rounded-md border border-[var(--campus-line)] px-3 py-2 text-sm"
          value={group}
          onChange={(e) => setGroup(e.target.value)}
        >
          <option value="">Select a group…</option>
          {(groups.data ?? []).map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        <input
          type="date"
          className="rounded-md border border-[var(--campus-line)] px-3 py-2 text-sm"
          value={day}
          onChange={(e) => setDay(e.target.value)}
        />
      </div>

      {!group ? (
        <EmptyState message="Choose a group to see its roster." />
      ) : students.isLoading || records.isLoading ? (
        <Spinner />
      ) : roster.length === 0 ? (
        <EmptyState message="No students have this group as their primary group." />
      ) : (
        <Card>
          <table className="w-full text-sm">
            <tbody>
              {roster.map((s) => {
                const r = recFor(s.id);
                return (
                  <tr
                    key={s.id}
                    className="border-b border-[var(--campus-line)] last:border-0"
                  >
                    <td className="px-3 py-2.5 font-medium">
                      {s.display_name}
                    </td>
                    <td className="px-3 py-2.5">
                      {!r ? (
                        <Badge>Not marked</Badge>
                      ) : r.status === "ABSENT" ? (
                        <Badge tone="red">Absent</Badge>
                      ) : r.checked_out_at ? (
                        <Badge tone="neutral">
                          Out {time(r.checked_out_at)}
                        </Badge>
                      ) : r.checked_in_at ? (
                        <Badge tone="green">In {time(r.checked_in_at)}</Badge>
                      ) : (
                        <Badge>{label(r.status)}</Badge>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <span className="flex justify-end gap-1">
                        {!r?.checked_in_at && r?.status !== "ABSENT" && (
                          <>
                            <Button size="sm" onClick={() => checkIn(s)}>
                              Check in
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => absent(s)}
                            >
                              Absent
                            </Button>
                          </>
                        )}
                        {r?.checked_in_at && !r?.checked_out_at && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setCheckout({ rec: r, student: s })}
                          >
                            Check out
                          </Button>
                        )}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}

      <Modal
        open={!!checkout}
        onClose={() => setCheckout(null)}
        title={
          checkout ? `Check out — ${checkout.student.display_name}` : "Check out"
        }
      >
        {checkout && (
          <CheckoutPicker
            pickups={(pickups.data ?? []).filter(
              (p) => p.student === checkout.student.id,
            )}
            links={(links.data ?? []).filter(
              (l) => l.student === checkout.student.id && l.can_pickup,
            )}
            onPick={(body) => doCheckout(checkout.rec.id, body)}
          />
        )}
      </Modal>
    </div>
  );
}

function CheckoutPicker({
  pickups,
  links,
  onPick,
}: {
  pickups: Pickup[];
  links: Link[];
  onPick: (body: Record<string, string>) => void;
}) {
  const [choice, setChoice] = useState("");
  const opts = [
    ...pickups.map((p) => ({ v: `pickup:${p.id}`, l: `${p.name} (authorized pickup)` })),
    ...links.map((l) => ({
      v: `link:${l.id}`,
      l: `${l.guardian_name ?? "Guardian"} (guardian)`,
    })),
  ];
  return (
    <div className="space-y-4">
      {opts.length === 0 ? (
        <p className="text-sm text-red-600">
          No authorized pickup or pickup-cleared guardian is on file for this
          child. Add one on the student record first.
        </p>
      ) : (
        <select
          className="w-full rounded-md border border-[var(--campus-line)] px-3 py-2 text-sm"
          value={choice}
          onChange={(e) => setChoice(e.target.value)}
        >
          <option value="">Released to…</option>
          {opts.map((o) => (
            <option key={o.v} value={o.v}>
              {o.l}
            </option>
          ))}
        </select>
      )}
      <div className="flex justify-end">
        <Button
          disabled={!choice}
          onClick={() => {
            const [kind, id] = choice.split(":");
            onPick(
              kind === "pickup"
                ? { pickup_id: id }
                : { guardian_link_id: id },
            );
          }}
        >
          Confirm check-out
        </Button>
      </div>
    </div>
  );
}
