"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useList } from "@/lib/hooks";
import { whoami } from "@/lib/auth";
import { auditSummary } from "@/lib/audit";
import { PageHeader, Card, Spinner, Badge } from "@/components/ui";
import { date, time, today, label } from "@/lib/format";

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

const OFFICE = ["SUPERADMIN", "ADMIN", "FRONT_DESK"];
const ADMIN_TIER = ["SUPERADMIN", "ADMIN"];

function Stat({
  label: lbl,
  value,
  href,
  tone = "sky",
}: {
  label: string;
  value: number | string;
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
      </Card>
    </Link>
  );
}

export default function DashboardPage() {
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: whoami });
  const role = me?.role ?? "";
  const isOffice = OFFICE.includes(role);
  const isAdminTier = ADMIN_TIER.includes(role);

  const students = useList<{ id: string }>("students", { page: 1 });
  const apps = useList<{ id: number }>(
    "applications",
    { status: "SUBMITTED" },
    isOffice,
  );
  const invoices = useList<{ id: number }>(
    "invoices",
    { status: "ISSUED" },
    isOffice,
  );
  const threads = useList<{ id: number }>("message-threads");
  const incidents = useList<Incident>("incident-reports", { status: "SENT" });
  const sessions = useList<Session>("sessions", { date: today() });

  const security = useQuery({
    queryKey: ["audit-summary"],
    queryFn: auditSummary,
    enabled: isAdminTier,
    refetchInterval: 60_000,
  });

  const loading = students.isLoading || sessions.isLoading;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle={
          isAdminTier
            ? "The day at a glance, plus recent security activity — counts link through."
            : "A quick read on the day — counts link through to the full lists."
        }
      />

      {loading ? (
        <Spinner />
      ) : (
        <>
          <div className="campus-stagger grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Stat
              label="Students on file"
              value={students.data?.count ?? 0}
              href="/people/"
              tone="sky"
            />
            {isOffice && (
              <Stat
                label="Applications to review"
                value={apps.data?.count ?? 0}
                href="/registration/"
                tone="amber"
              />
            )}
            {isOffice && (
              <Stat
                label="Issued invoices"
                value={invoices.data?.count ?? 0}
                href="/billing/"
                tone="emerald"
              />
            )}
            <Stat
              label="Message threads"
              value={threads.data?.count ?? 0}
              href="/communication/"
              tone="violet"
            />
            <Stat
              label="Open incidents"
              value={incidents.data?.count ?? 0}
              href="/communication/"
              tone="rose"
            />
            <Stat
              label="Sessions today"
              value={sessions.data?.count ?? 0}
              href="/scheduling/"
              tone="slate"
            />
          </div>

          {isAdminTier && (
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
              {security.isLoading ? (
                <Spinner />
              ) : (
                <div className="grid grid-cols-2 gap-px bg-[var(--campus-line)] sm:grid-cols-4">
                  {[
                    ["Failed sign-ins", security.data?.login_failed ?? 0, "security"],
                    ["Lockouts", security.data?.lockout ?? 0, "security"],
                    ["Access denied", security.data?.permission_denied ?? 0, "security"],
                    ["Exports / erasures", security.data?.governance ?? 0, "governance"],
                  ].map(([lbl, n, set]) => (
                    <Link
                      key={lbl as string}
                      href={`/audit/?set=${set}`}
                      className="bg-[var(--campus-bg,#fff)] px-4 py-3 hover:bg-black/[0.02] dark:bg-transparent"
                    >
                      <div
                        className={`text-xl font-semibold ${
                          (n as number) > 0 ? "text-[var(--campus-fg)]" : "text-[var(--campus-muted)]"
                        }`}
                      >
                        {n as number}
                      </div>
                      <div className="text-xs text-[var(--campus-muted)]">{lbl as string}</div>
                    </Link>
                  ))}
                </div>
              )}
            </Card>
          )}

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
                      <span className="font-medium">
                        {s.group_name ?? "Group"}
                      </span>{" "}
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
        </>
      )}
    </div>
  );
}
