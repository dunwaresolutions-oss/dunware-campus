"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useQueryParam } from "@/lib/hooks";
import { getGuardian } from "@/lib/guardians";
import { apiMessage, label } from "@/lib/format";
import { Badge, Card, ErrorNote, PageHeader, Spinner } from "@/components/ui";

type Tone = "neutral" | "green" | "amber" | "red" | "sky" | "violet";

const STATUS_TONE: Record<string, Tone> = {
  ACTIVE: "green",
  INACTIVE: "neutral",
  WITHDRAWN: "amber",
};

export default function GuardianDetailPage() {
  const id = useQueryParam("id");

  const guardian = useQuery({
    queryKey: ["guardian", id],
    queryFn: () => getGuardian(id as string),
    enabled: !!id,
  });

  if (!id) return null;
  if (guardian.isLoading) return <Spinner />;
  if (guardian.isError) return <ErrorNote message={apiMessage(guardian.error)} />;
  if (!guardian.data) return null;
  const g = guardian.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${g.first_name} ${g.last_name}`}
        subtitle={`${g.school_name}${g.school_district ? ` — ${g.school_district}` : ""}`}
      />

      <Card className="p-5">
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--campus-muted)]">Email</dt>
            <dd className="mt-0.5 text-sm">{g.email || "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-[var(--campus-muted)]">Phone</dt>
            <dd className="mt-0.5 text-sm">{g.phone || "—"}</dd>
          </div>
        </dl>
      </Card>

      <Card className="p-5">
        <h2 className="mb-2 text-sm font-semibold">
          Children ({g.children.length})
        </h2>
        {g.children.length === 0 ? (
          <p className="text-sm text-[var(--campus-muted)]">None synced.</p>
        ) : (
          <ul className="divide-y divide-[var(--campus-line)] text-sm">
            {g.children.map((c, i) => (
              <li key={i} className="flex items-center justify-between py-2">
                {c.student_id ? (
                  <Link href={`/students/detail/?id=${c.student_id}`} className="hover:underline">
                    {c.name}
                    <span className="ml-2 text-xs text-[var(--campus-muted)]">{label(c.relationship)}</span>
                  </Link>
                ) : (
                  <span>
                    {c.name}
                    <span className="ml-2 text-xs text-[var(--campus-muted)]">{label(c.relationship)}</span>
                  </span>
                )}
                <span className="flex items-center gap-2 text-[var(--campus-muted)]">
                  {c.student_number}
                  {c.status && <Badge tone={STATUS_TONE[c.status] ?? "neutral"}>{label(c.status)}</Badge>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
