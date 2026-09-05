"use client";

import Link from "next/link";
import { useList } from "@/lib/hooks";
import { PageHeader, Card, Spinner, Badge } from "@/components/ui";
import { date, time, today } from "@/lib/format";

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

function Stat({
  label,
  value,
  href,
}: {
  label: string;
  value: number | string;
  href: string;
}) {
  return (
    <Link href={href}>
      <Card className="p-4 transition hover:border-sky-300">
        <div className="text-2xl font-semibold text-neutral-900">{value}</div>
        <div className="mt-1 text-xs text-neutral-500">{label}</div>
      </Card>
    </Link>
  );
}

export default function DashboardPage() {
  const students = useList<{ id: string }>("students", { page: 1 });
  const apps = useList<{ id: number }>("applications", { status: "SUBMITTED" });
  const invoices = useList<{ id: number }>("invoices", { status: "ISSUED" });
  const threads = useList<{ id: number }>("message-threads");
  const incidents = useList<Incident>("incident-reports", { status: "SENT" });
  const sessions = useList<Session>("sessions", { date: today() });

  const loading =
    students.isLoading ||
    apps.isLoading ||
    invoices.isLoading ||
    sessions.isLoading;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="A quick read on the day — counts link through to the full lists."
      />

      {loading ? (
        <Spinner />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Stat
              label="Students on file"
              value={students.data?.count ?? 0}
              href="/people/"
            />
            <Stat
              label="Applications to review"
              value={apps.data?.count ?? 0}
              href="/registration/"
            />
            <Stat
              label="Issued invoices"
              value={invoices.data?.count ?? 0}
              href="/billing/"
            />
            <Stat
              label="Message threads"
              value={threads.data?.count ?? 0}
              href="/communication/"
            />
            <Stat
              label="Open incidents"
              value={incidents.data?.count ?? 0}
              href="/communication/"
            />
            <Stat
              label="Sessions today"
              value={sessions.data?.count ?? 0}
              href="/scheduling/"
            />
          </div>

          <div className="mt-8 grid gap-6 lg:grid-cols-2">
            <Card>
              <div className="border-b border-neutral-100 px-4 py-3 text-sm font-semibold">
                Today&apos;s sessions
              </div>
              <div className="divide-y divide-neutral-100">
                {(sessions.data?.results ?? []).length === 0 && (
                  <div className="p-4 text-sm text-neutral-500">
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
                      <span className="text-neutral-500">
                        {s.room_name ?? ""}
                      </span>
                    </span>
                    <span className="text-neutral-500">
                      {time(s.starts_at)}
                    </span>
                  </div>
                ))}
              </div>
            </Card>

            <Card>
              <div className="border-b border-neutral-100 px-4 py-3 text-sm font-semibold">
                Open incident reports
              </div>
              <div className="divide-y divide-neutral-100">
                {(incidents.data?.results ?? []).length === 0 && (
                  <div className="p-4 text-sm text-neutral-500">
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
                      <span className="text-neutral-500">{i.category}</span>
                    </span>
                    <Badge tone="amber">{i.status}</Badge>
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
