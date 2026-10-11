import { api } from "./api";

export interface DashboardFigures {
  school_count: number;
  enrolment_total: number;
  attendance_pct: number | null;
  consent_compliance_pct: number | null;
  incidents_by_category: Record<string, number>;
  illness_count: number;
  illness_rate_per_100_students: number | null;
}

export interface DashboardByDistrict {
  by_district: (DashboardFigures & { district: string })[];
}

export interface DashboardQuery {
  schoolId?: string;
  groupByDistrict?: boolean;
}

function queryString(q: DashboardQuery): string {
  const params = new URLSearchParams();
  if (q.schoolId) params.set("school_id", q.schoolId);
  if (q.groupByDistrict) params.set("group_by", "district");
  const s = params.toString();
  return s ? `?${s}` : "";
}

export function getDashboard(
  q: DashboardQuery & { groupByDistrict?: false },
): Promise<DashboardFigures>;
export function getDashboard(
  q: DashboardQuery & { groupByDistrict: true },
): Promise<DashboardByDistrict>;
export function getDashboard(q: DashboardQuery = {}) {
  return api(`/central/dashboard/${queryString(q)}`);
}

/** The CSV export endpoint returns `text/csv`, not JSON -- this bypasses
 * lib/api.ts's `api()` helper (which always tries to JSON-parse the body)
 * and triggers a normal browser download instead. GET needs no CSRF token. */
export async function downloadDashboardCsv(q: DashboardQuery = {}): Promise<void> {
  const API_BASE =
    process.env.NEXT_PUBLIC_API_BASE && process.env.NODE_ENV === "development"
      ? process.env.NEXT_PUBLIC_API_BASE
      : "";
  const res = await fetch(`${API_BASE}/api/central/dashboard/export.csv${queryString(q)}`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Export failed (HTTP ${res.status}).`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "central-dashboard.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
