"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { isStaff, logout, whoami } from "@/lib/auth";
import {
  portalDashboard,
  payInvoices,
  requestContactChange,
  submitConsent,
  type ContactChangeRequest,
  type PortalChild,
  type PortalInvoice,
  type PortalThreadSummary,
} from "@/lib/portal";
import { Card, Spinner, Badge, Button } from "@/components/ui";
import { Modal } from "@/components/Modal";
import { RecordForm } from "@/components/RecordForm";
import { ScheduleCalendar } from "@/components/ScheduleCalendar";
import { useToast } from "@/components/Toast";
import { api } from "@/lib/api";
import { list, create } from "@/lib/resource";
import { date, datetime, time, money, label, apiMessage } from "@/lib/format";
import type { CalendarSession } from "@/lib/calendar";

/* ------------------------------------------------------------------ icons */
/* A small hand-drawn set (no icon-library dependency) — 22x22, stroke-only,
 * currentColor, so they inherit whatever tone wraps them. */

type IconProps = { className?: string };
const iconBase = "h-[18px] w-[18px]";
const svgProps = {
  viewBox: "0 0 24 24",
  fill: "none" as const,
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const CalendarIcon = ({ className = iconBase }: IconProps) => (
  <svg className={className} {...svgProps}>
    <rect x="3" y="4.5" width="18" height="16" rx="2.5" />
    <path d="M3 9.5h18M8 2.5v4M16 2.5v4" />
  </svg>
);
const CheckCircleIcon = ({ className = iconBase }: IconProps) => (
  <svg className={className} {...svgProps}>
    <circle cx="12" cy="12" r="9" />
    <path d="m8.5 12.3 2.3 2.3 4.7-5" />
  </svg>
);
const FileTextIcon = ({ className = iconBase }: IconProps) => (
  <svg className={className} {...svgProps}>
    <path d="M7 2.5h7l4 4v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1v-17a1 1 0 0 1 1-1Z" />
    <path d="M14 2.5v4h4M9 12.5h6M9 16.5h6" />
  </svg>
);
const DollarIcon = ({ className = iconBase }: IconProps) => (
  <svg className={className} {...svgProps}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v10M15 9.7c0-1.2-1.3-2.2-3-2.2s-3 .9-3 2.1 1.3 1.9 3 2.1c1.7.2 3 .9 3 2.1s-1.3 2.2-3 2.2-3-1-3-2.2" />
  </svg>
);
const StarIcon = ({ className = iconBase }: IconProps) => (
  <svg className={className} {...svgProps}>
    <path d="m12 3 2.7 5.9 6.3.7-4.7 4.4 1.3 6.3L12 17.2l-5.6 3.1 1.3-6.3-4.7-4.4 6.3-.7Z" />
  </svg>
);
const BookOpenIcon = ({ className = iconBase }: IconProps) => (
  <svg className={className} {...svgProps}>
    <path d="M12 6.5c-1.5-1.3-3.8-2-6.5-2-1 0-1.5.2-1.5.2v13.6s.5-.2 1.5-.2c2.7 0 5 .7 6.5 2 1.5-1.3 3.8-2 6.5-2 1 0 1.5.2 1.5.2V4.7s-.5-.2-1.5-.2c-2.7 0-5 .7-6.5 2Z" />
    <path d="M12 6.5v13.6" />
  </svg>
);
const AlertIcon = ({ className = iconBase }: IconProps) => (
  <svg className={className} {...svgProps}>
    <path d="M10.6 3.5 2.2 18a1.5 1.5 0 0 0 1.3 2.2h17a1.5 1.5 0 0 0 1.3-2.2L13.4 3.5a1.5 1.5 0 0 0-2.8 0Z" />
    <path d="M12 9.5v4.2M12 17v.1" />
  </svg>
);
const MessageIcon = ({ className = iconBase }: IconProps) => (
  <svg className={className} {...svgProps}>
    <path d="M4 5.5h16a1 1 0 0 1 1 1v9.6a1 1 0 0 1-1 1H9l-4.4 3.2a.6.6 0 0 1-.95-.48V17.1H4a1 1 0 0 1-1-1v-9.6a1 1 0 0 1 1-1Z" />
  </svg>
);
const MegaphoneIcon = ({ className = iconBase }: IconProps) => (
  <svg className={className} {...svgProps}>
    <path d="M3 10v4a1 1 0 0 0 1 1h2l7 4.5v-15L6 9H4a1 1 0 0 0-1 1Z" />
    <path d="M17 8.5a5 5 0 0 1 0 7M20 6a8.5 8.5 0 0 1 0 12" />
  </svg>
);
const InboxIcon = ({ className = iconBase }: IconProps) => (
  <svg className={className} {...svgProps}>
    <path d="M3.5 12h4.2l1.6 2.4h5.4L16.3 12h4.2" />
    <path d="M5.2 5.5h13.6a1 1 0 0 1 1 .82L21 12v6a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18v-6l1.2-5.68a1 1 0 0 1 1-.82Z" />
  </svg>
);
const CreditCardIcon = ({ className = iconBase }: IconProps) => (
  <svg className={className} {...svgProps}>
    <rect x="2.5" y="5.5" width="19" height="13" rx="2" />
    <path d="M2.5 9.5h19M6 14.5h4" />
  </svg>
);
const ShieldIcon = ({ className = iconBase }: IconProps) => (
  <svg className={className} {...svgProps}>
    <path d="M12 2.7 4.5 5.5v6c0 5 3.2 8.4 7.5 10 4.3-1.6 7.5-5 7.5-10v-6Z" />
    <path d="m8.7 12.1 2.2 2.2 4.4-4.6" />
  </svg>
);
const LogOutIcon = ({ className = iconBase }: IconProps) => (
  <svg className={className} {...svgProps}>
    <path d="M9 20H5.5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1H9M14.5 16.5 19 12l-4.5-4.5M8.5 12H19" />
  </svg>
);

/* ---------------------------------------------------------------- helpers */

type BadgeTone = "neutral" | "green" | "amber" | "red" | "sky" | "violet";
const ATTENDANCE_TONE: Record<string, { dot: string; badge: BadgeTone }> = {
  PRESENT: { dot: "bg-emerald-500", badge: "green" },
  LATE: { dot: "bg-amber-500", badge: "amber" },
  ABSENT: { dot: "bg-red-500", badge: "red" },
  EXCUSED: { dot: "bg-sky-500", badge: "sky" },
  LEFT_EARLY: { dot: "bg-violet-500", badge: "violet" },
  EXPECTED: { dot: "bg-neutral-300 dark:bg-neutral-600", badge: "neutral" },
};

function greetingWord(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

function avatarBg(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  const hue = h % 360;
  return `hsl(${hue} 62% 45%)`;
}

/* ------------------------------------------------------------------- page */

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
  const [activeChild, setActiveChild] = useState<string | null>(null);
  const [payFor, setPayFor] = useState<string | null>(null);

  useEffect(() => {
    if (!meLoading && !me) router.replace("/login/");
    if (!meLoading && me && isStaff(me.role)) router.replace("/");
  }, [meLoading, me, router]);

  const children = dash.data?.children ?? [];
  useEffect(() => {
    if (!activeChild && children.length > 0) setActiveChild(children[0].id);
  }, [activeChild, dash.data?.children]);

  if (meLoading || !me || isStaff(me.role)) return null;

  const child = children.find((c) => c.id === activeChild) ?? children[0] ?? null;

  return (
    <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-10">
      {/* ---- header ---------------------------------------------------- */}
      <div className="campus-enter mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-[var(--campus-accent)]">
            {greetingWord()}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-[var(--campus-fg)] sm:text-3xl">
            {me.display_name || me.username}
          </h1>
        </div>
        <Button
          variant="ghost"
          onClick={async () => {
            await logout();
            router.replace("/login/");
          }}
        >
          <LogOutIcon />
          Sign out
        </Button>
      </div>

      {dash.isLoading ? (
        <Spinner />
      ) : dash.isError ? (
        <Card className="p-6 text-sm text-red-600">Couldn&apos;t load your dashboard.</Card>
      ) : (
        <div className="campus-stagger space-y-6">
          <AttentionStrip students={children} collectsFees={dash.data?.collects_fees ?? true} />

          {children.length > 1 && (
            <ChildSwitcher
              childrenList={children}
              activeId={child?.id ?? null}
              onPick={setActiveChild}
            />
          )}

          {child && (
            <ChildDashboard
              key={child.id}
              child={child}
              collectsFees={dash.data?.collects_fees ?? true}
              onConsent={() => dash.refetch()}
              onPay={() => setPayFor(child.id)}
            />
          )}

          <div className="grid gap-5 lg:grid-cols-2">
            <AnnouncementsCard announcements={dash.data?.announcements ?? []} />
            <MessagesCard threads={dash.data?.message_threads ?? []} />
          </div>

          <RequestsCard
            requests={dash.data?.contact_change_requests ?? []}
            onNew={() => setContactFor(true)}
          />
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

      <PayInvoicesModal
        open={!!payFor}
        onClose={() => setPayFor(null)}
        childrenList={children}
        currency={dash.data?.currency ?? "CAD"}
        preselectChildId={payFor}
      />
    </div>
  );
}

/* -------------------------------------------------------- attention strip */

function AttentionStrip({
  students,
  collectsFees,
}: {
  students: PortalChild[];
  collectsFees: boolean;
}) {
  const pendingConsents = students.reduce((n, c) => n + c.pending_consents.length, 0);
  const outstandingCents = collectsFees
    ? students.reduce(
        (sum, c) =>
          sum +
          c.invoices
            .filter((i) => i.status !== "PAID" && i.status !== "VOID")
            .reduce((s, i) => s + i.balance_cents, 0),
        0,
      )
    : 0;
  const openIncidents = students.reduce((n, c) => n + c.open_incidents.length, 0);

  const items: { icon: ReactNode; text: string; tone: "amber" | "red" }[] = [];
  if (pendingConsents > 0) {
    items.push({
      icon: <ShieldIcon />,
      text: `${pendingConsents} consent${pendingConsents === 1 ? "" : "s"} need${pendingConsents === 1 ? "s" : ""} your decision`,
      tone: "amber",
    });
  }
  if (outstandingCents > 0) {
    items.push({
      icon: <DollarIcon />,
      text: `${money(outstandingCents)} outstanding`,
      tone: "amber",
    });
  }
  if (openIncidents > 0) {
    items.push({
      icon: <AlertIcon />,
      text: `${openIncidents} incident report${openIncidents === 1 ? "" : "s"} to review`,
      tone: "red",
    });
  }
  if (items.length === 0) return null;

  const toneCls = {
    amber: "border-amber-300/60 bg-amber-50/80 text-amber-800 dark:border-amber-800/50 dark:bg-amber-950/40 dark:text-amber-300",
    red: "border-red-300/60 bg-red-50/80 text-red-800 dark:border-red-800/50 dark:bg-red-950/40 dark:text-red-300",
  };

  return (
    <div className="flex flex-wrap gap-2.5">
      {items.map((it, i) => (
        <div
          key={i}
          className={`flex items-center gap-2 rounded-xl border px-3.5 py-2 text-sm font-medium ${toneCls[it.tone]}`}
        >
          {it.icon}
          {it.text}
        </div>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------- switcher */

function ChildSwitcher({
  childrenList,
  activeId,
  onPick,
}: {
  childrenList: PortalChild[];
  activeId: string | null;
  onPick: (id: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {childrenList.map((c) => {
        const active = c.id === activeId;
        return (
          <button
            key={c.id}
            onClick={() => onPick(c.id)}
            className={`flex items-center gap-2.5 rounded-full py-1.5 pl-1.5 pr-4 text-sm font-medium transition-all duration-150 ${
              active
                ? "glass ring-2 ring-[var(--campus-accent)]"
                : "border border-[var(--campus-line)] text-[var(--campus-muted)] hover:text-[var(--campus-fg)]"
            }`}
          >
            <span
              className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-semibold text-white"
              style={{ background: avatarBg(c.id) }}
            >
              {initials(c.display_name)}
            </span>
            {c.display_name}
          </button>
        );
      })}
    </div>
  );
}

/* --------------------------------------------------------- section shell */

function SectionCard({
  icon,
  title,
  action,
  children,
  tone = "neutral",
}: {
  icon: ReactNode;
  title: string;
  action?: ReactNode;
  children: ReactNode;
  tone?: "neutral" | "amber";
}) {
  return (
    <Card className="p-4 sm:p-5">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            className={`grid h-8 w-8 place-items-center rounded-lg ${
              tone === "amber"
                ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                : "bg-[var(--campus-accent-soft)] text-[var(--campus-accent)]"
            }`}
          >
            {icon}
          </span>
          <h3 className="text-sm font-semibold">{title}</h3>
        </div>
        {action}
      </div>
      {children}
    </Card>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-[var(--campus-muted)]">{children}</p>;
}

/* -------------------------------------------------------- child dashboard */

function ChildDashboard({
  child,
  collectsFees,
  onConsent,
  onPay,
}: {
  child: PortalChild;
  collectsFees: boolean;
  onConsent: () => void;
  onPay: () => void;
}) {
  const toast = useToast();
  const [consenting, setConsenting] = useState<string | null>(null);
  const [rcPreview, setRcPreview] = useState<{ id: string; html: string } | null>(null);
  const [rcLoading, setRcLoading] = useState<string | null>(null);
  const [openSession, setOpenSession] = useState<CalendarSession | null>(null);

  async function openReportCard(id: string) {
    setRcLoading(id);
    try {
      const res = await api<{ html: string }>(`/report-cards/${id}/preview/`);
      setRcPreview({ id, html: res.html });
    } catch {
      toast("error", "Could not open the report card");
    } finally {
      setRcLoading(null);
    }
  }

  const attendanceSorted = [...child.recent_attendance].sort(
    (a, b) => a.date.localeCompare(b.date),
  );
  const lastStatus = attendanceSorted[attendanceSorted.length - 1]?.status;

  return (
    <div className="space-y-4">
      {/* Always-visible context: which child's data is on screen. The
       * chip-based switcher above only appears with >1 child and only
       * shows *active* state via a ring — neither says so in words, and
       * with exactly one child there's no switcher at all. */}
      <div className="flex items-center gap-2.5 text-sm text-[var(--campus-muted)]">
        <span
          className="grid h-6 w-6 shrink-0 place-items-center rounded-full text-[10px] font-semibold text-white"
          style={{ background: avatarBg(child.id) }}
        >
          {initials(child.display_name)}
        </span>
        Viewing <span className="font-semibold text-[var(--campus-fg)]">{child.display_name}</span>
        <span className="text-xs">· {child.student_number}</span>
      </div>

      {child.pending_consents.length > 0 && (
        <SectionCard icon={<ShieldIcon />} title="Consents needed" tone="amber">
          <div className="flex flex-wrap gap-2">
            {child.pending_consents.map((k) => (
              <div
                key={k}
                className="flex items-center gap-2 rounded-lg border border-[var(--campus-line)] px-3 py-1.5"
              >
                <span className="text-sm font-medium">{label(k)}</span>
                <Button
                  size="sm"
                  variant="primary"
                  disabled={consenting === k}
                  onClick={async () => {
                    setConsenting(k);
                    try {
                      await submitConsent({ student: child.id, kind: k, granted: true });
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
                  disabled={consenting === k}
                  onClick={async () => {
                    setConsenting(k);
                    try {
                      await submitConsent({ student: child.id, kind: k, granted: false });
                      toast("info", `${label(k)} consent withheld`);
                      onConsent();
                    } catch {
                      toast("error", "Could not record");
                    } finally {
                      setConsenting(null);
                    }
                  }}
                >
                  Decline
                </Button>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      <SectionCard icon={<CalendarIcon />} title="Upcoming schedule">
        <ScheduleCalendar
          groups={[]}
          fixedStudentId={child.id}
          calendarEndpoint="/portal/calendar/"
          initialView="week"
          onOpenSession={setOpenSession}
        />
      </SectionCard>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <SectionCard
          icon={<CheckCircleIcon />}
          title="Attendance"
          action={
            lastStatus && (
              <Badge tone={ATTENDANCE_TONE[lastStatus]?.badge ?? "neutral"}>
                {label(lastStatus)}
              </Badge>
            )
          }
        >
          {attendanceSorted.length === 0 ? (
            <Empty>Nothing recorded yet.</Empty>
          ) : (
            <>
              <div className="mb-2.5 flex gap-1.5">
                {attendanceSorted.slice(-14).map((a) => (
                  <span
                    key={a.id}
                    title={`${date(a.date)} — ${label(a.status)}`}
                    className={`h-2.5 flex-1 rounded-full ${ATTENDANCE_TONE[a.status]?.dot ?? "bg-neutral-300"}`}
                  />
                ))}
              </div>
              <ul className="space-y-1 text-sm text-[var(--campus-muted)]">
                {attendanceSorted
                  .slice(-3)
                  .reverse()
                  .map((a) => (
                    <li key={a.id} className="flex justify-between">
                      <span>{date(a.date)}</span>
                      <span>{label(a.status)}</span>
                    </li>
                  ))}
              </ul>
            </>
          )}
        </SectionCard>

        <SectionCard icon={<FileTextIcon />} title="Report cards">
          {child.released_report_cards.length === 0 ? (
            <Empty>None released yet.</Empty>
          ) : (
            <ul className="space-y-2">
              {child.released_report_cards.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-2 text-sm">
                  <span>Released {date(r.released_at)}</span>
                  <Button
                    size="sm"
                    variant="subtle"
                    disabled={rcLoading === r.id}
                    onClick={() => openReportCard(r.id)}
                  >
                    {rcLoading === r.id ? "Opening…" : "View"}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        {collectsFees && (
          <SectionCard
            icon={<DollarIcon />}
            title="Billing"
            action={
              child.invoices.some(
                (i) => i.status !== "VOID" && i.status !== "PAID" && i.balance_cents > 0,
              ) && (
                <Button size="sm" onClick={onPay}>
                  <CreditCardIcon className="h-[14px] w-[14px]" />
                  Pay
                </Button>
              )
            }
          >
            {child.invoices.length === 0 ? (
              <Empty>Nothing on file.</Empty>
            ) : (
              <ul className="space-y-2">
                {child.invoices.map((i) => (
                  <li key={i.id} className="flex items-center justify-between text-sm">
                    <span>
                      {money(i.total_cents)}
                      {i.due_date && (
                        <span className="text-xs text-[var(--campus-muted)]"> · due {date(i.due_date)}</span>
                      )}
                    </span>
                    <span className="flex items-center gap-2">
                      {i.balance_cents > 0 && i.status !== "VOID" && (
                        <span className="text-xs font-medium text-[var(--campus-muted)]">
                          bal {money(i.balance_cents)}
                        </span>
                      )}
                      <Badge
                        tone={
                          i.status === "PAID"
                            ? "green"
                            : i.status === "OVERDUE"
                              ? "red"
                              : i.status === "VOID"
                                ? "neutral"
                                : "amber"
                        }
                      >
                        {label(i.status)}
                      </Badge>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>
        )}

        {child.upcoming_bookings.length > 0 && (
          <SectionCard icon={<StarIcon />} title="After-school activities">
            <ul className="space-y-2 text-sm">
              {child.upcoming_bookings.map((b) => (
                <li key={b.id} className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate">{b.offering}</span>
                  <span className="flex shrink-0 items-center gap-2 text-xs text-[var(--campus-muted)]">
                    {datetime(b.starts_at)}
                    <Badge tone={b.status === "CANCELLED" ? "red" : "sky"}>{label(b.status)}</Badge>
                  </span>
                </li>
              ))}
            </ul>
          </SectionCard>
        )}

        {child.ieps.length > 0 && (
          <SectionCard icon={<BookOpenIcon />} title="Individual Education Plan">
            {child.ieps.map((p) => (
              <div key={p.id} className="mb-2 last:mb-0">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-medium">{p.primary_concern || "IEP"}</span>
                  <Badge tone={p.status === "ACTIVE" ? "green" : "neutral"}>{label(p.status)}</Badge>
                </div>
                {p.review_date && (
                  <p className="text-xs text-[var(--campus-muted)]">Next review {date(p.review_date)}</p>
                )}
                {p.goals.length > 0 && (
                  <ul className="mt-1 space-y-0.5 text-xs text-[var(--campus-muted)]">
                    {p.goals.map((g, i) => (
                      <li key={i}>
                        {g.area} — {g.progress}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
            <p className="mt-2 text-xs text-[var(--campus-muted)]">
              Contact the school for the full plan.
            </p>
          </SectionCard>
        )}

        {child.open_incidents.length > 0 && (
          <SectionCard icon={<AlertIcon />} title="Incident reports" tone="amber">
            <ul className="space-y-1.5 text-sm">
              {child.open_incidents.map((inc) => (
                <li key={inc.id} className="flex items-center justify-between gap-2">
                  <span>{label(inc.category)}</span>
                  <span className="text-xs text-[var(--campus-muted)]">{date(inc.occurred_at)}</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-[var(--campus-muted)]">
              See Messages for acknowledgement, if requested by the school.
            </p>
          </SectionCard>
        )}
      </div>

      <Modal
        open={!!rcPreview}
        onClose={() => setRcPreview(null)}
        title={`Report card — ${child.display_name}`}
        wide
      >
        {rcPreview && (
          <iframe
            title="Report card"
            srcDoc={rcPreview.html}
            className="h-[70vh] w-full rounded-lg border border-[var(--campus-line)] bg-white"
          />
        )}
      </Modal>

      <Modal
        open={!!openSession}
        onClose={() => setOpenSession(null)}
        title={openSession?.title || "Session"}
      >
        {openSession && (
          <div className="space-y-1 text-sm">
            <div>
              {date(openSession.date)} · {time(openSession.start_time)}–{time(openSession.end_time)}
            </div>
            {openSession.room_name && (
              <div className="text-[var(--campus-muted)]">{openSession.room_name}</div>
            )}
            {openSession.status === "CANCELLED" && (
              <div className="text-red-600">
                Cancelled{openSession.cancelled_reason ? `: ${openSession.cancelled_reason}` : ""}
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}

/* ------------------------------------------------------------- pay invoices */

interface PayableRow {
  invoice: PortalInvoice;
  childId: string;
  childName: string;
}

function payableRows(childrenList: PortalChild[]): PayableRow[] {
  const rows: PayableRow[] = [];
  for (const c of childrenList) {
    for (const inv of c.invoices) {
      if (inv.status !== "VOID" && inv.status !== "PAID" && inv.balance_cents > 0) {
        rows.push({ invoice: inv, childId: c.id, childName: c.display_name });
      }
    }
  }
  return rows;
}

function PayInvoicesModal({
  open,
  onClose,
  childrenList,
  currency,
  preselectChildId,
}: {
  open: boolean;
  onClose: () => void;
  childrenList: PortalChild[];
  currency: string;
  preselectChildId: string | null;
}) {
  const toast = useToast();
  const rows = payableRows(childrenList);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [amount, setAmount] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Pre-check the invoices for whichever child's "Pay" button was clicked —
  // every other outstanding invoice (siblings included) stays visible and
  // unchecked, so the parent decides whether to combine them (2026-09-16
  // decision: "the parent should decide which invoices to combine at
  // checkout").
  useEffect(() => {
    if (!open) return;
    const initial = new Set<string>();
    for (const c of childrenList) {
      if (preselectChildId && c.id !== preselectChildId) continue;
      for (const inv of c.invoices) {
        if (inv.status !== "VOID" && inv.status !== "PAID" && inv.balance_cents > 0) {
          initial.add(inv.id);
        }
      }
    }
    setSelected(initial);
  }, [open, preselectChildId, childrenList]);

  const selectedRows = rows.filter((r) => selected.has(r.invoice.id));
  const selectedTotalCents = selectedRows.reduce((s, r) => s + r.invoice.balance_cents, 0);

  // Reset the amount to the new full total whenever the selection changes -
  // but typing in the field doesn't itself change selectedTotalCents, so
  // this doesn't fight the parent while they're editing it down.
  useEffect(() => {
    setAmount(selectedTotalCents > 0 ? (selectedTotalCents / 100).toFixed(2) : "");
  }, [selectedTotalCents]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const amountCents = Math.round((parseFloat(amount) || 0) * 100);
  const amountValid = amountCents > 0 && amountCents <= selectedTotalCents;

  async function pay() {
    if (!amountValid || selected.size === 0) return;
    setSubmitting(true);
    try {
      const attempt = await payInvoices({
        invoice_ids: [...selected],
        amount_cents: amountCents,
        return_url: `${window.location.origin}/portal/pay/return/`,
      });
      if (!attempt.checkout_url) throw new Error("No checkout link came back.");
      try {
        // The return page reads this first; Paystack/Flutterwave also echo
        // our reference back as a callback query param, so this is a
        // fallback for Stripe (session_id only) and for storage that
        // doesn't survive the round trip, not the only path.
        sessionStorage.setItem("campus_pending_payment_ref", attempt.reference);
      } catch {
        // Private browsing / storage disabled - fine, see above.
      }
      window.location.href = attempt.checkout_url;
    } catch (e) {
      toast("error", apiMessage(e));
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Pay invoices">
      {rows.length === 0 ? (
        <Empty>Nothing outstanding.</Empty>
      ) : (
        <div className="space-y-4">
          <p className="text-xs text-[var(--campus-muted)]">
            Select one or more invoices to pay together in a single charge — useful if
            you&apos;re paying for more than one child at once.
          </p>
          <ul className="max-h-64 space-y-1.5 overflow-y-auto">
            {rows.map((r) => (
              <li key={r.invoice.id}>
                <label className="flex cursor-pointer items-center justify-between gap-2 rounded-lg border border-[var(--campus-line)] px-3 py-2 text-sm hover:bg-black/[0.02] dark:hover:bg-white/[0.03]">
                  <span className="flex items-center gap-2.5">
                    <input
                      type="checkbox"
                      checked={selected.has(r.invoice.id)}
                      onChange={() => toggle(r.invoice.id)}
                      className="h-4 w-4 rounded border-[var(--campus-line)]"
                    />
                    <span>
                      <span className="block font-medium">{r.childName}</span>
                      <span className="text-xs text-[var(--campus-muted)]">
                        {r.invoice.due_date ? `due ${date(r.invoice.due_date)}` : "no due date"}
                      </span>
                    </span>
                  </span>
                  <span className="font-medium">{money(r.invoice.balance_cents, currency)}</span>
                </label>
              </li>
            ))}
          </ul>

          <div className="flex items-center justify-between border-t border-[var(--campus-line)] pt-3 text-sm">
            <span className="text-[var(--campus-muted)]">Selected balance</span>
            <span className="font-semibold">{money(selectedTotalCents, currency)}</span>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--campus-muted)]">
              Amount to pay now
            </label>
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              disabled={selected.size === 0}
              className="w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm text-[var(--campus-fg)] focus:border-[var(--campus-accent)] focus:outline-none disabled:opacity-50"
            />
            {amount !== "" && !amountValid && (
              <p className="mt-1 text-xs text-red-600">
                Enter an amount greater than zero and no more than the selected balance.
              </p>
            )}
            <p className="mt-1 text-xs text-[var(--campus-muted)]">
              Paying less than the full balance is allowed — the rest stays owing.
            </p>
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button disabled={!amountValid || selected.size === 0 || submitting} onClick={pay}>
              {submitting
                ? "Starting checkout…"
                : `Pay ${amount ? money(amountCents, currency) : ""}`}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

/* ------------------------------------------------------------ announcements */

function AnnouncementsCard({
  announcements,
}: {
  announcements: { id: string; title: string; body: string; published_at: string; pinned: boolean }[];
}) {
  const [expanded, setExpanded] = useState(false);
  const sorted = [...announcements].sort((a, b) =>
    a.pinned === b.pinned ? b.published_at.localeCompare(a.published_at) : a.pinned ? -1 : 1,
  );
  const shown = expanded ? sorted : sorted.slice(0, 3);

  return (
    <SectionCard icon={<MegaphoneIcon />} title="Announcements">
      {sorted.length === 0 ? (
        <Empty>Nothing new.</Empty>
      ) : (
        <>
          <ul className="space-y-3">
            {shown.map((a) => (
              <li key={a.id} className="border-b border-[var(--campus-line)] pb-3 last:border-0 last:pb-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{a.title}</span>
                  {a.pinned && <Badge tone="sky">Pinned</Badge>}
                </div>
                <p className="mt-0.5 text-sm text-[var(--campus-muted)]">{a.body}</p>
                <p className="mt-1 text-xs text-[var(--campus-muted)]">{datetime(a.published_at)}</p>
              </li>
            ))}
          </ul>
          {sorted.length > 3 && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="mt-2 text-xs font-medium text-[var(--campus-accent)] hover:underline"
            >
              {expanded ? "Show less" : `Show ${sorted.length - 3} more`}
            </button>
          )}
        </>
      )}
    </SectionCard>
  );
}

/* ----------------------------------------------------------------- messages */

function MessagesCard({ threads }: { threads: PortalThreadSummary[] }) {
  const [open, setOpen] = useState<PortalThreadSummary | null>(null);
  const sorted = [...threads].sort((a, b) =>
    (b.last_message_at ?? "").localeCompare(a.last_message_at ?? ""),
  );

  return (
    <SectionCard icon={<MessageIcon />} title="Messages">
      {sorted.length === 0 ? (
        <Empty>No conversations with the school yet.</Empty>
      ) : (
        <ul className="space-y-1">
          {sorted.map((t) => (
            <li key={t.id}>
              <button
                onClick={() => setOpen(t)}
                className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-2 text-left text-sm transition-colors hover:bg-black/[0.03] dark:hover:bg-white/[0.05]"
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">{t.subject}</span>
                  <span className="text-xs text-[var(--campus-muted)]">
                    {t.message_count} message{t.message_count === 1 ? "" : "s"}
                    {t.last_message_at ? ` · ${datetime(t.last_message_at)}` : ""}
                  </span>
                </span>
                {t.closed && <Badge tone="neutral">Closed</Badge>}
              </button>
            </li>
          ))}
        </ul>
      )}

      <Modal open={!!open} onClose={() => setOpen(null)} title={open?.subject ?? "Conversation"}>
        {open && <ThreadMessages thread={open} />}
      </Modal>
    </SectionCard>
  );
}

interface ThreadMessage {
  id: string;
  body: string;
  sender_name?: string;
  created_at: string;
}

function ThreadMessages({ thread }: { thread: PortalThreadSummary }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const q = useQuery({
    queryKey: ["portal-thread-messages", thread.id],
    queryFn: () => list<ThreadMessage>("messages", { thread: thread.id }),
  });

  async function send() {
    if (!body.trim()) return;
    setSending(true);
    try {
      await create("messages", { thread: thread.id, body });
      setBody("");
      qc.invalidateQueries({ queryKey: ["portal-thread-messages", thread.id] });
      qc.invalidateQueries({ queryKey: ["portal"] });
    } catch (e) {
      toast("error", apiMessage(e));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="max-h-80 space-y-2.5 overflow-y-auto rounded-lg bg-black/[0.03] p-3 dark:bg-white/[0.04]">
        {q.isLoading ? (
          <Spinner />
        ) : (q.data?.results ?? []).length === 0 ? (
          <Empty>No messages yet.</Empty>
        ) : (
          (q.data?.results ?? []).map((m) => (
            <div key={m.id} className="text-sm">
              <span className="text-xs text-[var(--campus-muted)]">
                {datetime(m.created_at)}
                {m.sender_name ? ` — ${m.sender_name}` : ""}
              </span>
              <p>{m.body}</p>
            </div>
          ))
        )}
      </div>
      {!thread.closed && (
        <div className="flex gap-2">
          <input
            className="flex-1 rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm text-[var(--campus-fg)] focus:border-[var(--campus-accent)] focus:outline-none"
            placeholder="Write a reply…"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
          />
          <Button size="sm" disabled={sending || !body.trim()} onClick={send}>
            Send
          </Button>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ requests */

function RequestsCard({
  requests,
  onNew,
}: {
  requests: ContactChangeRequest[];
  onNew: () => void;
}) {
  return (
    <SectionCard
      icon={<InboxIcon />}
      title="My requests"
      action={
        <Button size="sm" onClick={onNew}>
          Request a change
        </Button>
      }
    >
      {requests.length === 0 ? (
        <Empty>No open requests.</Empty>
      ) : (
        <ul className="space-y-1.5 text-sm">
          {requests.map((r) => (
            <li key={r.id} className="flex items-center gap-2">
              <span>
                {label(r.field)} → {r.proposed_value}
              </span>
              <Badge
                tone={r.status === "APPROVED" ? "green" : r.status === "REJECTED" ? "red" : "amber"}
              >
                {label(r.status)}
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
