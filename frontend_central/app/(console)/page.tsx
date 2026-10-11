"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listSchools } from "@/lib/schools";
import { downloadDashboardCsv, getDashboard, type DashboardFigures } from "@/lib/dashboard";
import { useToast } from "@/components/Toast";
import { apiMessage } from "@/lib/format";
import { Button, Card, ErrorNote, PageHeader, Spinner } from "@/components/ui";

function Figures({ data }: { data: DashboardFigures }) {
  const incidentEntries = Object.entries(data.incidents_by_category);
  return (
    <div className="campus-stagger grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Card className="p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-[var(--campus-muted)]">Schools</p>
        <p className="mt-1 text-3xl font-semibold">{data.school_count}</p>
      </Card>
      <Card className="p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-[var(--campus-muted)]">Active enrolment</p>
        <p className="mt-1 text-3xl font-semibold">{data.enrolment_total}</p>
      </Card>
      <Card className="p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-[var(--campus-muted)]">Attendance</p>
        <p className="mt-1 text-3xl font-semibold">
          {data.attendance_pct == null ? "—" : `${data.attendance_pct}%`}
        </p>
      </Card>
      <Card className="p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-[var(--campus-muted)]">Consent compliance</p>
        <p className="mt-1 text-3xl font-semibold">
          {data.consent_compliance_pct == null ? "—" : `${data.consent_compliance_pct}%`}
        </p>
      </Card>
      <Card className="p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-[var(--campus-muted)]">
          Illness rate (per 100 students)
        </p>
        <p className="mt-1 text-3xl font-semibold">
          {data.illness_rate_per_100_students == null ? "—" : data.illness_rate_per_100_students}
        </p>
        <p className="mt-1 text-xs text-[var(--campus-muted)]">{data.illness_count} illness incident(s) recorded</p>
      </Card>
      <Card className="p-5 sm:col-span-2 lg:col-span-4">
        <p className="text-xs font-medium uppercase tracking-wide text-[var(--campus-muted)]">Incidents by category</p>
        {incidentEntries.length === 0 ? (
          <p className="mt-2 text-sm text-[var(--campus-muted)]">None recorded.</p>
        ) : (
          <div className="mt-3 flex flex-wrap gap-4">
            {incidentEntries.map(([category, count]) => (
              <div key={category} className="text-sm">
                <span className="text-[var(--campus-muted)]">{category}:</span>{" "}
                <span className="font-semibold">{count}</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

export default function DashboardPage() {
  const toast = useToast();
  const [schoolId, setSchoolId] = useState("");
  const [byDistrict, setByDistrict] = useState(false);
  const [exporting, setExporting] = useState(false);

  const schools = useQuery({ queryKey: ["schools"], queryFn: listSchools });

  const overall = useQuery({
    queryKey: ["dashboard", schoolId, byDistrict],
    queryFn: () => getDashboard({ schoolId: schoolId || undefined, groupByDistrict: false }),
    enabled: !byDistrict,
  });
  const districts = useQuery({
    queryKey: ["dashboard-by-district", schoolId],
    queryFn: () => getDashboard({ schoolId: schoolId || undefined, groupByDistrict: true }),
    enabled: byDistrict,
  });

  async function onExport() {
    setExporting(true);
    try {
      await downloadDashboardCsv({ schoolId: schoolId || undefined, groupByDistrict: byDistrict });
    } catch (err) {
      toast("error", apiMessage(err));
    } finally {
      setExporting(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Aggregate figures only — never an individual student, guardian or staff record."
        actions={
          <Button variant="ghost" onClick={onExport} disabled={exporting}>
            {exporting ? "Exporting…" : "Download CSV"}
          </Button>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <select
          className="rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm"
          value={schoolId}
          onChange={(e) => setSchoolId(e.target.value)}
          disabled={byDistrict}
        >
          <option value="">All schools</option>
          {(schools.data ?? []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-[var(--campus-muted)]">
          <input
            type="checkbox"
            checked={byDistrict}
            onChange={(e) => setByDistrict(e.target.checked)}
          />
          Group by district
        </label>
      </div>

      {byDistrict ? (
        districts.isLoading ? (
          <Spinner />
        ) : districts.isError ? (
          <ErrorNote message={apiMessage(districts.error)} />
        ) : (
          <div className="space-y-6">
            {/* Sorted highest illness rate first -- the point of grouping by
                district for health-concern monitoring is spotting which one
                stands out, not scanning an arbitrary list. */}
            {[...(districts.data?.by_district ?? [])]
              .sort(
                (a, b) =>
                  (b.illness_rate_per_100_students ?? -1) - (a.illness_rate_per_100_students ?? -1),
              )
              .map((row) => (
                <div key={row.district}>
                  <h2 className="mb-2 text-sm font-semibold text-[var(--campus-muted)]">{row.district}</h2>
                  <Figures data={row} />
                </div>
              ))}
          </div>
        )
      ) : overall.isLoading ? (
        <Spinner />
      ) : overall.isError ? (
        <ErrorNote message={apiMessage(overall.error)} />
      ) : overall.data ? (
        <Figures data={overall.data} />
      ) : null}
    </div>
  );
}
