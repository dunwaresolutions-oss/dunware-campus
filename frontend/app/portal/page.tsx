"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { isStaff, logout, whoami } from "@/lib/auth";
import {
  portalDashboard,
  requestContactChange,
  submitConsent,
  type PortalChild,
} from "@/lib/portal";
import { Card, PageHeader, Spinner, Badge, Button } from "@/components/ui";
import { Modal } from "@/components/Modal";
import { RecordForm } from "@/components/RecordForm";
import { useToast } from "@/components/Toast";
import { date, datetime, money, label } from "@/lib/format";

export default function PortalPage() {
  const router = useRouter();
  const toast = useToast();
  const { data: me, isLoading: meLoading } = useQuery({
    queryKey: ["me"],
    queryFn: whoami,
  });
  const dash = useQuery({
    queryKey: ["portal"],
    queryFn: portalDashboard,
    enabled: !!me && !isStaff(me.role),
  });
  const [contactFor, setContactFor] = useState(false);

  useEffect(() => {
    if (!meLoading && !me) router.replace("/login/");
    if (!meLoading && me && isStaff(me.role)) router.replace("/");
  }, [meLoading, me, router]);

  if (meLoading || !me || isStaff(me.role)) return null;

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="mb-6 flex items-center justify-between">
        <PageHeader
          title={`Hello, ${me.display_name || me.username}`}
          subtitle="Your children's schedule, attendance, report cards, bookings, messages, and forms."
        />
        <Button
          variant="ghost"
          onClick={async () => {
            await logout();
            router.replace("/login/");
          }}
        >
          Sign out
        </Button>
      </div>

      {dash.isLoading ? (
        <Spinner />
      ) : dash.isError ? (
        <p className="text-sm text-red-600">
          Couldn&apos;t load your dashboard.
        </p>
      ) : (
        <div className="space-y-6">
          {(dash.data?.children ?? []).map((c) => (
            <ChildCard key={c.id} child={c} onConsent={() => dash.refetch()} />
          ))}

          <Card className="p-4">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold">Announcements</h3>
            </div>
            {(dash.data?.announcements ?? []).length === 0 && (
              <p className="text-sm text-[var(--campus-muted)]">Nothing new.</p>
            )}
            <ul className="space-y-2 text-sm">
              {(dash.data?.announcements ?? []).map((a) => (
                <li key={a.id}>
                  <span className="font-medium">{a.title}</span>{" "}
                  <span className="text-xs text-[var(--campus-muted)]">
                    {datetime(a.published_at)}
                  </span>
                  <p className="text-[var(--campus-muted)]">{a.body}</p>
                </li>
              ))}
            </ul>
          </Card>

          <Card className="p-4">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold">My requests</h3>
              <Button size="sm" onClick={() => setContactFor(true)}>
                Request a contact-detail change
              </Button>
            </div>
            {(dash.data?.contact_change_requests ?? []).length === 0 ? (
              <p className="text-sm text-[var(--campus-muted)]">No open requests.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {(dash.data?.contact_change_requests ?? []).map((r) => (
                  <li key={r.id} className="flex items-center gap-2">
                    <span>
                      {label(r.field)} → {r.proposed_value}
                    </span>
                    <Badge
                      tone={
                        r.status === "APPROVED"
                          ? "green"
                          : r.status === "REJECTED"
                            ? "red"
                            : "amber"
                      }
                    >
                      {label(r.status)}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}

      <Modal
        open={contactFor}
        onClose={() => setContactFor(false)}
        title="Request a contact-detail change"
      >
        <RecordForm
          fields={[
            {
              name: "field",
              label: "Field",
              type: "select",
              required: true,
              options: [
                "email",
                "phone",
                "address",
                "receives_communications",
                "lives_with",
              ].map((v) => ({ value: v, label: label(v) })),
            },
            { name: "proposed_value", label: "New value", required: true },
            { name: "reason", label: "Reason (optional)" },
          ]}
          submitLabel="Submit request"
          onSubmit={async (v) => {
            await requestContactChange(
              v as Parameters<typeof requestContactChange>[0],
            );
            toast("success", "Request submitted for staff approval");
            setContactFor(false);
            dash.refetch();
          }}
          onCancel={() => setContactFor(false)}
        />
      </Modal>
    </div>
  );
}

function ChildCard({
  child,
  onConsent,
}: {
  child: PortalChild;
  onConsent: () => void;
}) {
  const toast = useToast();
  const [consenting, setConsenting] = useState<string | null>(null);

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold">{child.display_name}</h3>
        <span className="text-xs text-[var(--campus-muted)]">#{child.student_number}</span>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <div className="text-xs font-semibold uppercase text-[var(--campus-muted)]">
            Upcoming sessions
          </div>
          {child.upcoming_sessions.length === 0 ? (
            <p className="text-sm text-[var(--campus-muted)]">None scheduled.</p>
          ) : (
            <ul className="text-sm">
              {child.upcoming_sessions.map((s) => (
                <li key={s.id}>
                  {date(s.date)} · {s.start_time?.slice(0, 5)} — {s.title}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <div className="text-xs font-semibold uppercase text-[var(--campus-muted)]">
            Recent attendance
          </div>
          {child.recent_attendance.length === 0 ? (
            <p className="text-sm text-[var(--campus-muted)]">Nothing recorded.</p>
          ) : (
            <ul className="text-sm">
              {child.recent_attendance.map((a) => (
                <li key={a.id}>
                  {date(a.date)} — {label(a.status)}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <div className="text-xs font-semibold uppercase text-[var(--campus-muted)]">
            Report cards
          </div>
          {child.released_report_cards.length === 0 ? (
            <p className="text-sm text-[var(--campus-muted)]">None released.</p>
          ) : (
            <ul className="text-sm">
              {child.released_report_cards.map((r) => (
                <li key={r.id}>Released {date(r.released_at)}</li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <div className="text-xs font-semibold uppercase text-[var(--campus-muted)]">
            Invoices
          </div>
          {child.invoices.length === 0 ? (
            <p className="text-sm text-[var(--campus-muted)]">Nothing outstanding.</p>
          ) : (
            <ul className="text-sm">
              {child.invoices.map((i) => (
                <li key={i.id}>
                  {money(i.total_cents)} · bal {money(i.balance_cents)} ·{" "}
                  {label(i.status)}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {child.pending_consents.length > 0 && (
        <div className="mt-4 rounded-md bg-amber-50 p-3">
          <div className="text-xs font-semibold uppercase text-amber-800">
            Consents needed
          </div>
          <div className="mt-1 flex flex-wrap gap-2">
            {child.pending_consents.map((k) => (
              <div key={k} className="flex items-center gap-1">
                <span className="text-sm">{label(k)}</span>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={consenting === k}
                  onClick={async () => {
                    setConsenting(k);
                    try {
                      await submitConsent({
                        student: child.id,
                        kind: k,
                        granted: true,
                      });
                      toast("success", `${label(k)} consent recorded`);
                      onConsent();
                    } catch {
                      toast("error", "Could not record consent");
                    } finally {
                      setConsenting(null);
                    }
                  }}
                >
                  Grant
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={async () => {
                    try {
                      await submitConsent({
                        student: child.id,
                        kind: k,
                        granted: false,
                      });
                      toast("info", `${label(k)} consent withheld`);
                      onConsent();
                    } catch {
                      toast("error", "Could not record");
                    }
                  }}
                >
                  Decline
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
