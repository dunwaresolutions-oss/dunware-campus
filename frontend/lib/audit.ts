import { api } from "./api";

export interface AuditRow {
  id: string;
  at: string;
  actor_label: string;
  actor_role: string;
  source_ip: string | null;
  action: string;
  object_type: string;
  object_id: string;
  summary: string;
  changed_fields: string[];
}

export interface AuditSummary {
  since: string;
  login_failed: number;
  lockout: number;
  permission_denied: number;
  logins: number;
  governance: number;
  total: number;
}

export function auditSummary(): Promise<AuditSummary> {
  return api<AuditSummary>("/audit/summary/");
}
