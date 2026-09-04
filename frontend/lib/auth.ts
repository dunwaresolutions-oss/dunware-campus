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
  /** a confirmed TOTP device exists for this account */
  mfa_enrolled?: boolean;
  /** the current session has cleared the second factor */
  mfa_verified?: boolean;
  /** staff account with no device yet — route to /console/mfa/setup */
  mfa_enrollment_required?: boolean;
}

export interface MfaSetup {
  otpauth_uri: string;
  secret: string;
  /** data: URI, ready for an <img src> */
  qr: string;
}

/** Thrown by `login()` when the account has MFA and the code was missing/wrong. */
export class MfaRequiredError extends Error {
  constructor() {
    super("A valid authentication code is required.");
    this.name = "MfaRequiredError";
  }
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

/** Begin TOTP enrolment — returns the QR + secret to show the user. */
export async function mfaSetup(): Promise<MfaSetup> {
  await ensureCsrf();
  return api<MfaSetup>("/auth/mfa/setup/", { method: "POST", body: "{}" });
}

/** Confirm enrolment (or re-verify this session) with a code from the app. */
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
