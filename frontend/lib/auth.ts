import { api, ensureCsrf } from "./api";

export type Role =
  | "SUPERADMIN"
  | "ADMIN"
  | "TEACHER"
  | "TUTOR"
  | "FRONT_DESK"
  | "PARENT"
  | "STUDENT";

export interface CurrentUser {
  id: string;
  username: string;
  email: string;
  role: Role;
  display_name: string;
  must_use_mfa: boolean;
}

export const STAFF_ROLES: Role[] = [
  "SUPERADMIN",
  "ADMIN",
  "TEACHER",
  "TUTOR",
  "FRONT_DESK",
];

export const isStaff = (r: Role | undefined) => !!r && STAFF_ROLES.includes(r);

export async function whoami(): Promise<CurrentUser | null> {
  try {
    return await api<CurrentUser>("/auth/whoami/");
  } catch {
    return null;
  }
}

export async function login(
  username: string,
  password: string,
  otp?: string,
): Promise<CurrentUser> {
  await ensureCsrf();
  return api<CurrentUser>("/auth/login/", {
    method: "POST",
    body: JSON.stringify({ username, password, otp }),
  });
}

export async function logout(): Promise<void> {
  await api("/auth/logout/", { method: "POST" });
}
