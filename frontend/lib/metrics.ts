import { api } from "./api";

export type ScopeLevel = "instructor" | "office" | "system";

export interface Metrics {
  generated_at: string;
  scope: {
    level: ScopeLevel;
    role: string;
    group_count: number;
    student_count: number;
    active_students: number;
    term: string | null;
  };
  attendance: {
    window_days: number;
    records: number;
    rate_pct: number | null;
    present: number;
    absent: number;
    late: number;
    excused: number;
    chronic_absentees: number;
    unmarked_today: number;
  };
  enrolment: {
    active: number;
    prospective: number;
    graduated: number;
    withdrawn_term: number;
    by_status: Record<string, number>;
    capacity_pct?: number | null;
    waitlist?: number;
    student_staff_ratio?: number | null;
    applications?: {
      submitted: number;
      under_review: number;
      offer_made: number;
      waitlisted: number;
      enrolled: number;
      declined: number;
      offer_acceptance_pct: number | null;
    };
  };
  academics: {
    assessments: number;
    assessments_released: number;
    released_pct: number | null;
    grading_completion_pct: number | null;
    avg_mark_pct: number | null;
    report_cards: {
      draft: number;
      finalized: number;
      released: number;
      released_pct: number | null;
    };
  };
  wellbeing: {
    window_days: number;
    incidents: number;
    incidents_open: number;
    per_100_students: number | null;
    by_severity: Record<string, number>;
    by_category: Record<string, number>;
    observations: number;
  };
  operations?: {
    billing: {
      issued: number;
      invoiced_cents: number;
      collected_cents: number;
      outstanding_cents: number;
      overdue: number;
      collection_pct: number | null;
    };
    consent: {
      active_students: number;
      by_kind: Record<string, number | null>;
      fully_covered_pct: number | null;
    };
    booking: {
      upcoming_slots: number;
      seats: number;
      confirmed: number;
      waitlisted: number;
      fill_pct: number | null;
    };
    messages: { threads_open: number; threads_total: number };
  };
  system?: {
    security_24h: {
      failed_signins: number;
      lockouts: number;
      access_denied: number;
      exports_erasures: number;
      total: number;
    };
    staffing: {
      by_role: Record<string, number>;
      total_active: number;
      groups_without_lead: number;
      mfa_coverage_pct: number | null;
    };
    backup: {
      configured: boolean;
      last_success_at: string | null;
      last_success_age_hours: number | null;
      last_success_bytes: number | null;
      last_status: string | null;
      last_error: string;
      runs_7d: number;
      failures_7d: number;
      archives_retained: number | null;
      last_verified_at: string | null;
      stale: boolean;
    };
    platform?: {
      legal_holds: number;
      anonymized_records: number;
      retention_eligible: number;
      audit_24h_total: number;
    };
  };
}

export const fetchMetrics = () => api<Metrics>("/metrics/");
