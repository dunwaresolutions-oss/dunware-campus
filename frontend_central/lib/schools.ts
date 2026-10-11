import { api, ensureCsrf } from "./api";

export interface School {
  id: string;
  name: string;
  district: string;
  sync_status: "NEVER_SYNCED" | "OK" | "ERROR";
  last_synced_at: string | null;
  snapshot_schema_version: number | null;
  contact_email: string;
  active: boolean;
}

export interface SchoolWithToken extends School {
  /** Shown once -- never returned again by any later read. */
  sync_token: string;
}

export const listSchools = () => api<School[]>("/central/schools/");

export const getSchool = (id: string) => api<School>(`/central/schools/${id}/`);

export async function registerSchool(input: {
  name: string;
  district?: string;
  contact_email?: string;
}): Promise<SchoolWithToken> {
  await ensureCsrf();
  return api<SchoolWithToken>("/central/schools/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function rotateSchoolToken(id: string): Promise<SchoolWithToken> {
  await ensureCsrf();
  return api<SchoolWithToken>(`/central/schools/${id}/rotate-token/`, {
    method: "POST",
    body: "{}",
  });
}
