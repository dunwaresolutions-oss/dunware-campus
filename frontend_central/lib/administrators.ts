import { api } from "./api";
import type { Role } from "./auth";

export interface DirectoryUser {
  id: string;
  username: string;
  email: string;
  role: Role | "SUPERADMIN";
  is_active: boolean;
  status: string;
  display_name: string;
}

export const listDirectory = () => api<DirectoryUser[]>("/auth/users/");

export interface Invite {
  token: string;
  email: string;
  role: Role;
  expires_at: string;
}

export const inviteAdministrator = (input: { email: string; role: Role }) =>
  api<Invite>("/auth/invite/", { method: "POST", body: JSON.stringify(input) });

export interface DistrictAssignment {
  id: string;
  district: string;
}

export const listDistrictAssignments = (userId: string) =>
  api<DistrictAssignment[]>(`/central/district-assignments/?user_id=${userId}`);

export const addDistrictAssignment = (userId: string, district: string) =>
  api<DistrictAssignment>("/central/district-assignments/", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, district }),
  });

export const removeDistrictAssignment = (id: string) =>
  api<void>(`/central/district-assignments/${id}/`, { method: "DELETE" });
