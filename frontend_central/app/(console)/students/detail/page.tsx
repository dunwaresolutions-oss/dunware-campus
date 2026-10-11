"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useQueryParam } from "@/lib/hooks";
import { getStudent } from "@/lib/students";
import { apiMessage, date, label } from "@/lib/format";
import { Badge, Card, ErrorNote, PageHeader, Spinner } from "@/components/ui";

type Tone = "neutral" | "green" | "amber" | "red" | "sky" | "violet";

const STATUS_TONE: Record<string, Tone> = {
  ACTIVE: "green",
  INACTIVE: "neutral",
  WITHDRAWN: "amber",
};

export default function StudentDetailPage() {
  const id = useQueryParam("id");

  const student = useQuery({
    queryKey: ["student", id],
    queryFn: () => getStudent(id as string),
    enabled: !!id,
  });

  if (!id) return null;
  if (student.isLoading) return <Spinner />;
  if (student.isError) return <ErrorNote message={apiMessage(student.error)} />;
  if (!student.data) return null;
  const s = student.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${s.first_name} ${s.last_name}`}
        subtitle={`${s.school_name}${s.school_district ? ` — ${s.school_district}` : ""}`}
      />

      <Card className="p-5">
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--campus-muted)]">Student number</dt>
            <dd className="mt-0.5 text-sm">{s.student_number}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--campus-muted)]">Status</dt>
            <dd className="mt-0.5">
              <Badge tone={STATUS_TONE[s.status] ?? "neutral"}>{label(s.status)}</Badge>
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--campus-muted)]">Date of birth</dt>
            <dd className="mt-0.5 text-sm">{date(s.date_of_birth)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--campus-muted)]">Class / homeroom</dt>
            <dd className="mt-0.5 text-sm">{s.primary_group_name || "—"}</dd>
          </div>
        </dl>
      </Card>

      <Card className="p-5">
        <h2 className="mb-2 text-sm font-semibold">
          Guardians ({s.guardians.length})
        </h2>
        {s.guardians.length === 0 ? (
          <p className="text-sm text-[var(--campus-muted)]">None synced.</p>
        ) : (
          <ul className="divide-y divide-[var(--campus-line)] text-sm">
            {s.guardians.map((g) => (
              <li key={g.id} className="flex items-center justify-between py-2">
                <Link href={`/guardians/detail/?id=${g.id}`} className="hover:underline">
                  {g.name}
                  <span className="ml-2 text-xs text-[var(--campus-muted)]">{label(g.relationship)}</span>
                </Link>
                <span className="text-[var(--campus-muted)]">
                  {g.email}{g.phone ? ` · ${g.phone}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-5">
        <h2 className="mb-2 text-sm font-semibold">Enrolment history</h2>
        {s.enrolments.length === 0 ? (
          <p className="text-sm text-[var(--campus-muted)]">None synced.</p>
        ) : (
          <ul className="divide-y divide-[var(--campus-line)] text-sm">
            {s.enrolments.map((e, i) => (
              <li key={i} className="flex items-center justify-between py-2">
                <span>{e.group_name}</span>
                <span className="text-[var(--campus-muted)]">
                  {date(e.start_date)} – {e.end_date ? date(e.end_date) : "present"} · {label(e.status)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-5">
        <h2 className="mb-2 text-sm font-semibold">Attendance</h2>
        {s.attendance.length === 0 ? (
          <p className="text-sm text-[var(--campus-muted)]">None synced.</p>
        ) : (
          <ul className="divide-y divide-[var(--campus-line)] text-sm">
            {s.attendance.map((a, i) => (
              <li key={i} className="flex items-center justify-between py-2">
                <span>Present {a.present} · Absent {a.absent} · Late {a.late}</span>
                <span className="text-[var(--campus-muted)]">
                  {a.present_pct != null ? `${a.present_pct.toFixed(1)}%` : "—"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-5">
        <h2 className="mb-2 text-sm font-semibold">Consents</h2>
        {s.consents.length === 0 ? (
          <p className="text-sm text-[var(--campus-muted)]">None synced.</p>
        ) : (
          <ul className="divide-y divide-[var(--campus-line)] text-sm">
            {s.consents.map((c, i) => (
              <li key={i} className="flex items-center justify-between py-2">
                <span>{label(c.kind)} (v{c.version})</span>
                <Badge tone={c.granted ? "green" : "red"}>{c.granted ? "Granted" : "Not granted"}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-5">
        <h2 className="mb-2 text-sm font-semibold">Report cards</h2>
        {s.report_cards.length === 0 ? (
          <p className="text-sm text-[var(--campus-muted)]">None synced.</p>
        ) : (
          <ul className="divide-y divide-[var(--campus-line)] text-sm">
            {s.report_cards.map((r, i) => (
              <li key={i} className="flex items-center justify-between py-2">
                <span>Term</span>
                <Badge tone="neutral">{label(r.status)}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
