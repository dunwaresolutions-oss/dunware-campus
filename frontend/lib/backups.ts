import { list, type Page } from "./resource";

export interface BackupRun {
  id: string;
  kind: "SCHEDULED" | "MANUAL" | "VERIFY";
  status: "RUNNING" | "SUCCESS" | "FAILED";
  started_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
  archive_name: string;
  size_bytes: number | null;
  database_ok: boolean;
  media_ok: boolean;
  encrypted: boolean;
  archives_retained: number | null;
  error: string;
  host: string;
  build: string;
  triggered_by_label: string;
  created_at: string;
}

export const listBackups = (page = 1): Promise<Page<BackupRun>> =>
  list<BackupRun>("backups", { page });
