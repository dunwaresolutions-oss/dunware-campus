"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { search } from "@/lib/search";
import { apiMessage, label } from "@/lib/format";
import { Card, ErrorNote, PageHeader, Spinner } from "@/components/ui";

/** Refused outright for MINISTRY_ANALYST by the backend
 * (apps/central/permissions.py's IndividualRecordAccess) -- a 403 here
 * shows as an ErrorNote same as any other failure; the nav also hides this
 * page from that role so it's rarely actually reached by clicking around. */
export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");

  const results = useQuery({
    queryKey: ["search", submitted],
    queryFn: () => search(submitted),
    enabled: submitted.length > 0,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Search"
        subtitle="Across every school this account can see: students, guardians, staff."
      />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(query.trim());
        }}
        className="flex gap-2"
      >
        <input
          className="flex-1 rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2.5 text-sm"
          placeholder="Name, student number, email, username…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
      </form>

      {results.isLoading && <Spinner />}
      {results.isError && <ErrorNote message={apiMessage(results.error)} />}
      {results.data && (
        <div className="campus-stagger space-y-6">
          <Card className="p-5">
            <h2 className="mb-2 text-sm font-semibold">
              Students ({results.data.students.length})
            </h2>
            {results.data.students.length === 0 ? (
              <p className="text-sm text-[var(--campus-muted)]">No matches.</p>
            ) : (
              <ul className="divide-y divide-[var(--campus-line)] text-sm">
                {results.data.students.map((s) => (
                  <li key={s.id} className="flex items-center justify-between py-2">
                    <Link href={`/students/detail/?id=${s.id}`} className="hover:underline">
                      {s.name}
                      <span className="ml-2 text-xs text-[var(--campus-muted)]">
                        {s.school_name || "(unknown school)"}
                      </span>
                    </Link>
                    <span className="text-[var(--campus-muted)]">
                      {s.student_number} · {label(s.status)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card className="p-5">
            <h2 className="mb-2 text-sm font-semibold">
              Guardians ({results.data.guardians.length})
            </h2>
            {results.data.guardians.length === 0 ? (
              <p className="text-sm text-[var(--campus-muted)]">No matches.</p>
            ) : (
              <ul className="divide-y divide-[var(--campus-line)] text-sm">
                {results.data.guardians.map((g) => (
                  <li key={g.id} className="flex items-center justify-between py-2">
                    <Link href={`/guardians/detail/?id=${g.id}`} className="hover:underline">
                      {g.name}
                      <span className="ml-2 text-xs text-[var(--campus-muted)]">
                        {g.school_name || "(unknown school)"}
                      </span>
                    </Link>
                    <span className="text-[var(--campus-muted)]">{g.email}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card className="p-5">
            <h2 className="mb-2 text-sm font-semibold">Staff ({results.data.staff.length})</h2>
            {results.data.staff.length === 0 ? (
              <p className="text-sm text-[var(--campus-muted)]">No matches.</p>
            ) : (
              <ul className="divide-y divide-[var(--campus-line)] text-sm">
                {results.data.staff.map((s) => (
                  <li key={s.id} className="flex items-center justify-between py-2">
                    <span>
                      {s.username}
                      <span className="ml-2 text-xs text-[var(--campus-muted)]">
                        {s.school_name || "(unknown school)"}
                      </span>
                    </span>
                    <span className="text-[var(--campus-muted)]">{label(s.role)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
