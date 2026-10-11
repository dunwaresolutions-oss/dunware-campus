/**
 * Adapted from Campus's own frontend/lib/auth.ts -- same account-management
 * surface (apps.accounts, reused as-is on the backend), Central's own role
 * set. See docs/CENTRAL_SYNC_SCOPE.md's C0 decision 7 and C6 section.
 */
import { api, ensureCsrf } from "./api";

export type Role = "MINISTRY_ADMIN" | "MINISTRY_ANALYST" | "DISTRICT_OFFICER";

/** The bootstrap/break-glass account the shared first-run flow creates
 * (apps.accounts's SetupAdminView) always has this role, never one of the
 * three above -- see apps/central/permissions.py's own docstring on the
 * backend for why every endpoint treats it as a superset access level. */
export const BREAK_GLASS_ROLE = "SUPERADMIN" as const;

export interface CurrentUser {
  id: string;
  username: string;
  email: string;
  role: Role | typeof BREAK_GLASS_ROLE;
  display_name: string;
  must_use_mfa: boolean;
  mfa_enrolled?: boolean;
  mfa_verified?: boolean;
  mfa_enrollment_required?: boolean;
}

export interface MfaSetup {
  otpauth_uri: string;
  secret: string;
  qr: string;
}

export class MfaRequiredError extends Error {
  constructor() {
    super("A valid authentication code is required.");
    this.name = "MfaRequiredError";
  }
}

export const CENTRAL_ROLES: Role[] = [
  "MINISTRY_ADMIN",
  "MINISTRY_ANALYST",
  "DISTRICT_OFFICER",
];

export const isCentralRole = (r: Role | undefined) =>
  !!r && CENTRAL_ROLES.includes(r);

/** Can this account actually use the console -- one of the three Central
 * roles, or the break-glass bootstrap account. */
export const canUseConsole = (r: CurrentUser["role"] | undefined) =>
  !!r && (CENTRAL_ROLES.includes(r as Role) || r === BREAK_GLASS_ROLE);

/* --------------------------------------------------------- next= redirect */

const AUTH_FLOW_PREFIXES = ["/login/", "/mfa/", "/setup/"];

/** See Campus's own lib/auth.ts for the full reasoning this is copied from:
 * stops an open redirect, never an authorization check by itself. */
export function safeNextPath(raw: string | null | undefined): string | null {
  if (!raw) return null;
  if (raw.length > 1000) return null;
  if (!raw.startsWith("/")) return null;
  if (raw.startsWith("//") || raw.startsWith("/\\")) return null;
  if (/^\/[a-z][a-z0-9+.-]*:/i.test(raw)) return null;
  if (/[\r\n\t]/.test(raw)) return null;
  if (AUTH_FLOW_PREFIXES.some((p) => raw.startsWith(p))) return null;
  return raw;
}

export function loginRedirectUrl(): string {
  const next = window.location.pathname + window.location.search;
  return `/login/?next=${encodeURIComponent(next)}`;
}

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
  try {
    return await api<CurrentUser>("/auth/login/", {
      method: "POST",
      body: JSON.stringify({ username, password, otp }),
    });
  } catch (err) {
    const body = (err as { body?: { mfa_required?: boolean } })?.body;
    if (body?.mfa_required) throw new MfaRequiredError();
    throw err;
  }
}

export async function logout(): Promise<void> {
  await api("/auth/logout/", { method: "POST" });
}

/* ----------------------------------------------------- first-run setup */

export async function setupStatus(): Promise<{ needs_setup: boolean }> {
  try {
    return await api<{ needs_setup: boolean }>("/auth/setup/status/");
  } catch {
    return { needs_setup: false };
  }
}

export async function createFirstAdmin(input: {
  username: string;
  email: string;
  password: string;
}): Promise<CurrentUser> {
  await ensureCsrf();
  return api<CurrentUser>("/auth/setup/admin/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function mfaSetup(): Promise<MfaSetup> {
  await ensureCsrf();
  return api<MfaSetup>("/auth/mfa/setup/", { method: "POST", body: "{}" });
}

export async function mfaConfirm(token: string): Promise<void> {
  await ensureCsrf();
  await api("/auth/mfa/confirm/", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export interface MfaStatus {
  must_use_mfa: boolean;
  mfa_enrolled: boolean;
  mfa_verified: boolean;
}

export async function mfaStatus(): Promise<MfaStatus> {
  return api<MfaStatus>("/auth/mfa/status/");
}

/* --------------------------------------------------------- invite accept */

export async function acceptInvite(input: {
  token: string;
  username: string;
  password: string;
}): Promise<{ username: string }> {
  await ensureCsrf();
  return api("/auth/invite/accept/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
