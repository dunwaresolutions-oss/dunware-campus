"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { type ReactNode } from "react";
import { useList } from "@/lib/hooks";
import { whoami } from "@/lib/auth";
import { fetchMetrics, type Metrics } from "@/lib/metrics";
import { PageHeader, Card, Spinner, Badge } from "@/components/ui";
import { date, time, today, label, money } from "@/lib/format";

interface Session {
  id: number;
  group_name?: string;
  room_name?: string;
  starts_at: string;
  status: string;
}
interface Incident {
  id: number;
  student_name?: string;
  category: string;
  status: string;
  occurred_at: string;
}

const pct = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : `${n}%`;
const num = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : n.toLocaleString();

/* ------------------------------------------------------------------ pieces */

function Stat({
  label: lbl,
  value,
  sub,
  href,
  tone = "sky",
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  href: string;
  tone?: "sky" | "amber" | "emerald" | "violet" | "rose" | "slate";
}) {
  const bars: Record<string, string> = {
    sky: "before:bg-sky-400",
    amber: "before:bg-amber-400",
    emerald: "before:bg-emerald-400",
    violet: "before:bg-violet-400",
    rose: "before:bg-rose-400",
    slate: "before:bg-slate-400",
  };
  return (
    <Link href={href} className="block">
      <Card
        className={`relative overflow-hidden p-4 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[var(--campus-shadow-md)] before:absolute before:inset-y-0 before:left-0 before:w-1 ${bars[tone]}`}
      >
        <div className="text-2xl font-semibold tracking-tight text-[var(--campus-fg)]">
          {value}
        </div>
        <div className="mt-1 text-xs text-[var(--campus-muted)]">{lbl}</div>
        {sub && (
          <div className="mt-0.5 text-[11px] text-[var(--campus-muted)]">{sub}</div>
        )}
      </Card>
    </Link>
  );
}

function Section({
  title,
  href,
  children,
}: {
  title: string;
  href?: string;
  children: ReactNode;
}) {
  return (
    <Card>
      <div className="flex items-center justify-between border-b border-[var(--campus-line)] px-4 py-3">
        <span className="text-sm font-semibold">{title}</span>
        {href && (
          <Link
            href={href}
            className="text-xs font-medium text-[var(--campus-accent)] hover:underline"
          >
            Open →
          </Link>
        )}
      </div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 px-4 py-3 text-sm sm:grid-cols-3">
        {children}
      </dl>
    </Card>
  );
}

function Row({
  label: lbl,
  value,
  strong,
}: {
  label: string;
  value: ReactNode;
  strong?: boolean;
}) {
  return (
    <div className="contents">
      <dt className="col-span-1 text-[var(--campus-muted)]">{lbl}</dt>
      <dd
        className={`col-span-1 text-right sm:col-span-2 sm:text-left ${
          strong ? "font-semibold" : ""
        }`}
      >
        {value}
      </dd>
    </div>
  );
}

/* ---------------------------------------------------------------- sections */

function AttendanceSection({ m }: { m: Metrics }) {
  const a = m.attendance;
  return (
    <Section title={`Attendance · last ${a.window_days} days`} href="/attendance/">
      <Row label="Attendance rate" value={pct(a.rate_pct)} strong />
      <Row label="Records" value={num(a.records)} />
      <Row label="Absences" value={num(a.absent)} />
      <Row label="Late" value={num(a.late)} />
      <Row label="Excused" value={num(a.excused)} />
      <Row label="Chronic absentees" value={num(a.chronic_absentees)} />
      <Row label="Unmarked today" value={num(a.unmarked_today)} />
    </Section>
  );
}

function AcademicsSection({ m }: { m: Metrics }) {
  const a = m.academics;
  const rc = a.report_cards;
  return (
    <Section title="Academics" href="/grades/">
      <Row label="Assessments released" value={pct(a.released_pct)} strong />
      <Row
        label="Grading completion"
        value={pct(a.grading_completion_pct)}
        strong
      />
      <Row label="Average mark" value={pct(a.avg_mark_pct)} />
      <Row label="Assessments" value={num(a.assessments)} />
      <Row
        label="Report cards"
        value={`${num(rc.draft)} draft · ${num(rc.finalized)} final · ${num(
          rc.released,
        )} released`}
      />
      <Row label="Report cards released" value={pct(rc.released_pct)} />
    </Section>
  );
}

function WellbeingSection({ m }: { m: Metrics }) {
  const w = m.wellbeing;
  const sev = Object.entries(w.by_severity)
    .sort()
    .map(([k, v]) => `S${k}:${v}`)
    .join(" · ");
  return (
    <Section title={`Wellbeing · last ${w.window_days} days`} href="/communication/">
      <Row label="Incidents" value={num(w.incidents)} strong />
      <Row label="Open incidents" value={num(w.incidents_open)} strong />
      <Row label="Per 100 students" value={num(w.per_100_students)} />
      <Row label="Observations" value={num(w.observations)} />
      <Row label="By severity" value={sev || "—"} />
    </Section>
  );
}

function EnrolmentSection({ m }: { m: Metrics }) {
  const e = m.enrolment;
  const ap = e.applications;
  return (
    <Section title="Enrolment" href="/registration/">
      <Row label="Active students" value={num(e.active)} strong />
      <Row label="Prospective" value={num(e.prospective)} />
      <Row label="Withdrawn this term" value={num(e.withdrawn_term)} />
      {e.capacity_pct !== undefined && (
        <Row label="Capacity used" value={pct(e.capacity_pct)} strong />
      )}
      {e.waitlist !== undefined && (
        <Row label="Waitlisted" value={num(e.waitlist)} />
      )}
      {e.student_staff_ratio !== undefined && (
        <Row
          label="Student : instructor"
          value={e.student_staff_ratio === null ? "—" : `${e.student_staff_ratio} : 1`}
        />
      )}
      {ap && (
        <>
          <Row
            label="Applications"
            value={`${num(ap.submitted)} new · ${num(ap.under_review)} in review · ${num(
              ap.offer_made,
            )} offered`}
          />
          <Row label="Offer acceptance" value={pct(ap.offer_acceptance_pct)} />
        </>
      )}
    </Section>
  );
}

function OperationsSection({ m }: { m: Metrics }) {
  const o = m.operations;
  if (!o) return null;
  const b = o.billing;
  const c = o.consent;
  const bk = o.booking;
  const kinds = Object.entries(c.by_kind)
    .map(([k, v]) => `${label(k)} ${v === null ? "—" : `${v}%`}`)
    .join(" · ");
  return (
    <>
      <Section title="Billing" href="/billing/">
        <Row label="Invoiced" value={money(b.invoiced_cents)} strong />
        <Row label="Collected" value={money(b.collected_cents)} strong />
        <Row label="Outstanding" value={money(b.outstanding_cents)} strong />
        <Row label="Collection rate" value={pct(b.collection_pct)} />
        <Row label="Issued invoices" value={num(b.issued)} />
        <Row label="Overdue" value={num(b.overdue)} />
      </Section>
      <Section title="Consent, booking &amp; messages">
        <Row
          label="Consent — fully covered"
          value={pct(c.fully_covered_pct)}
          strong
        />
        <Row label="Consent by kind" value={kinds || "—"} />
        <Row label="Booking fill rate" value={pct(bk.fill_pct)} strong />
        <Row
          label="Upcoming slots"
          value={`${num(bk.upcoming_slots)} · ${num(bk.confirmed)}/${num(
            bk.seats,
          )} seats · ${num(bk.waitlisted)} waitlisted`}
        />
        <Row
          label="Message threads"
          value={`${num(o.messages.threads_open)} open / ${num(
            o.messages.threads_total,
          )} total`}
        />
      </Section>
    </>
  );
}

function SystemSection({ m }: { m: Metrics }) {
  const s = m.system;
  if (!s) return null;
  const st = s.staffing;
  const bk = s.backup;
  const roles = Object.entries(st.by_role)
    .map(([k, v]) => `${label(k)} ${v}`)
    .join(" · ");
  const backupVal = !bk.configured
    ? "not configured"
    : bk.last_success_at
      ? `${
          bk.last_success_age_hours != null
            ? `${bk.last_success_age_hours} h ago`
            : "recorded"
        }${bk.failures_7d ? ` · ${bk.failures_7d} failed (7d)` : ""}`
      : "never succeeded";
  return (
    <>
      <Card className="mt-6">
        <div className="flex items-center justify-between border-b border-[var(--campus-line)] px-4 py-3">
          <span className="text-sm font-semibold">Security · last 24 hours</span>
          <Link
            href="/audit/"
            className="text-xs font-medium text-[var(--campus-accent)] hover:underline"
          >
            Open the audit log →
          </Link>
        </div>
        <div className="grid grid-cols-2 gap-px bg-[var(--campus-line)] sm:grid-cols-4">
          {[
            ["Failed sign-ins", s.security_24h.failed_signins, "security"],
            ["Lockouts", s.security_24h.lockouts, "security"],
            ["Access denied", s.security_24h.access_denied, "security"],
            ["Exports / erasures", s.security_24h.exports_erasures, "governance"],
          ].map(([lbl, n, set]) => (
            <Link
              key={lbl as string}
              href={`/audit/?set=${set}`}
              className="bg-[var(--campus-bg,#fff)] px-4 py-3 hover:bg-black/[0.02] dark:bg-transparent"
            >
              <div
                className={`text-xl font-semibold ${
                  (n as number) > 0
                    ? "text-[var(--campus-fg)]"
                    : "text-[var(--campus-muted)]"
                }`}
              >
                {n as number}
              </div>
              <div className="text-xs text-[var(--campus-muted)]">
                {lbl as string}
              </div>
            </Link>
          ))}
        </div>
      </Card>

      <Section title="Staffing &amp; system" href="/staff/">
        <Row label="Active staff" value={num(st.total_active)} strong />
        <Row label="MFA coverage" value={pct(st.mfa_coverage_pct)} strong />
        <Row label="Groups without a lead" value={num(st.groups_without_lead)} />
        <Row label="By role" value={roles || "—"} />
        <Row
          label="Last backup"
          value={
            <span className={bk.stale ? "font-semibold text-amber-600" : ""}>
              {backupVal}
            </span>
          }
          strong
        />
        <Row
          label="Restore verified"
          value={bk.last_verified_at ? "yes" : "not yet"}
        />
        {s.platform && (
          <>
            <Row label="Legal holds" value={num(s.platform.legal_holds)} />
            <Row
              label="Anonymised records"
              value={num(s.platform.anonymized_records)}
            />
            <Row
              label="Retention-eligible"
              value={num(s.platform.retention_eligible)}
            />
            <Row label="Audit events (24h)" value={num(s.platform.audit_24h_total)} />
          </>
        )}
      </Section>
    </>
  );
}

/* -------------------------------------------------------------------- page */

const OFFICE = ["SUPERADMIN", "ADMIN", "FRONT_DESK"];

export default function DashboardPage() {
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: whoami });
  const role = me?.role ?? "";
  const isOffice = OFFICE.includes(role);

  const metrics = useQuery({
    queryKey: ["metrics"],
    queryFn: fetchMetrics,
    refetchInterval: 300_000,
  });
  const m = metrics.data;

  const incidents = useList<Incident>("incident-reports", { status: "SENT" });
  const sessions = useList<Session>("sessions", { date: today() });

  const scopeLine = m
    ? [
        m.scope.term,
        `${m.scope.group_count} ${m.scope.group_count === 1 ? "group" : "groups"}`,
        `${m.scope.student_count} students`,
        m.scope.level === "instructor"
          ? "your classes"
          : m.scope.level === "office"
            ? "school-wide"
            : "complete metrics",
      ]
        .filter(Boolean)
        .join(" · ")
    : "";

  return (
    <div>
      <PageHeader title="Dashboard" subtitle={scopeLine || "Loading metrics…"} />

      {metrics.isLoading || !m ? (
        <Spinner />
      ) : (
        <>
          <div className="campus-stagger grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Stat
              label="Attendance rate (30d)"
              value={pct(m.attendance.rate_pct)}
              href="/attendance/"
              tone="sky"
            />
            <Stat
              label="Active students"
              value={num(m.scope.active_students)}
              href="/people/"
              tone="violet"
            />
            <Stat
              label="Grading completion"
              value={pct(m.academics.grading_completion_pct)}
              href="/grades/"
              tone="emerald"
            />
            <Stat
              label="Open incidents"
              value={num(m.wellbeing.incidents_open)}
              href="/communication/"
              tone="rose"
            />
            {isOffice && m.operations && (
              <Stat
                label="Outstanding fees"
                value={money(m.operations.billing.outstanding_cents)}
                sub={`${pct(m.operations.billing.collection_pct)} collected`}
                href="/billing/?tab=invoices&outstanding=1"
                tone="amber"
              />
            )}
            <Stat
              label="Sessions today"
              value={num(sessions.data?.count ?? 0)}
              href="/scheduling/"
              tone="slate"
            />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <AttendanceSection m={m} />
            <AcademicsSection m={m} />
            <WellbeingSection m={m} />
            <EnrolmentSection m={m} />
            <OperationsSection m={m} />
          </div>

          <SystemSection m={m} />

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Card>
              <div className="border-b border-[var(--campus-line)] px-4 py-3 text-sm font-semibold">
                Today&apos;s sessions
              </div>
              <div className="divide-y divide-[var(--campus-line)]">
                {(sessions.data?.results ?? []).length === 0 && (
                  <div className="p-4 text-sm text-[var(--campus-muted)]">
                    Nothing scheduled for {date(today())}.
                  </div>
                )}
                {(sessions.data?.results ?? []).map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center justify-between px-4 py-2.5 text-sm"
                  >
                    <span>
                      <span className="font-medium">{s.group_name ?? "Group"}</span>{" "}
                      <span className="text-[var(--campus-muted)]">
                        {s.room_name ?? ""}
                      </span>
                    </span>
                    <span className="text-[var(--campus-muted)]">
                      {time(s.starts_at)}
                    </span>
                  </div>
                ))}
              </div>
            </Card>

            <Card>
              <div className="border-b border-[var(--campus-line)] px-4 py-3 text-sm font-semibold">
                Open incident reports
              </div>
              <div className="divide-y divide-[var(--campus-line)]">
                {(incidents.data?.results ?? []).length === 0 && (
                  <div className="p-4 text-sm text-[var(--campus-muted)]">
                    No incidents awaiting acknowledgement.
                  </div>
                )}
                {(incidents.data?.results ?? []).map((i) => (
                  <div
                    key={i.id}
                    className="flex items-center justify-between px-4 py-2.5 text-sm"
                  >
                    <span>
                      <span className="font-medium">
                        {i.student_name ?? "Student"}
                      </span>{" "}
                      <span className="text-[var(--campus-muted)]">
                        {label(i.category)}
                      </span>
                    </span>
                    <Badge tone="amber">{label(i.status)}</Badge>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <p className="mt-4 text-xs text-[var(--campus-muted)]">
            Metrics as of {time(m.generated_at)} · refreshes every few minutes.
          </p>
        </>
      )}
    </div>
  );
}
