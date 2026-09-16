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

/* --------------------------------------------------------- next= redirect */

// Pages that are themselves part of signing in — never a legitimate
// post-login destination, and pointing `next` at one risks a confusing
// "still on the login screen after logging in" dead end rather than an
// actual redirect loop (nothing here re-triggers on its own).
const AUTH_FLOW_PREFIXES = ["/login/", "/mfa/", "/setup/"];

/**
 * Validates a `next=` value pulled off a URL (always via
 * `URLSearchParams.get()`, which already percent-decodes it once — never
 * decode it again here, that's how a double-encoded value slips past a
 * naive check) before it's ever passed to `router.push`/`replace`.
 *
 * This exists solely to stop an open redirect: `next` must resolve to a
 * same-origin, same-document path, never something a browser would treat
 * as protocol-relative (`//evil.com`, `/\evil.com`) or an embedded scheme
 * (`/javascript:...`). It is NOT an authorization check — landing on
 * `next` never grants access to anything by itself. Every destination
 * page still runs its own existing auth/role guard off the session
 * cookie, and every API call it makes is still checked by the backend's
 * own permission classes exactly as before; this only decides whether a
 * string is a legitimate place in *this app* to point the browser.
 */
export function safeNextPath(raw: string | null | undefined): string | null {
  if (!raw) return null;
  if (raw.length > 1000) return null; // not a real path, don't bother
  if (!raw.startsWith("/")) return null;
  if (raw.startsWith("//") || raw.startsWith("/\\")) return null;
  if (/^\/[a-z][a-z0-9+.-]*:/i.test(raw)) return null; // e.g. "/javascript:..."
  if (/[\r\n\t]/.test(raw)) return null;
  if (AUTH_FLOW_PREFIXES.some((p) => raw.startsWith(p))) return null;
  return raw;
}

/** Everything under /portal/ is the parent/student area; everything else
 * authenticated is the staff console — used to keep a `next=` value from
 * sending the wrong role's post-login redirect into the other area (that
 * area's own guard would just bounce them straight back to /login/ with
 * the same next, landing on a "logged in but still see the login form"
 * dead end rather than anywhere useful). */
export const isPortalPath = (path: string) => path.startsWith("/portal");

/** Build `/login/?next=...` for an unauthenticated visit to a protected
 * route, so a successful sign-in can return here instead of the generic
 * default — call only from a client-only effect (reads window.location).
 * The three route guards (portal layout, portal page, console layout) all
 * funnel through this so the encoding is consistent everywhere. */
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

/** Unauthenticated: is the initial administrator still to be created? */
export async function setupStatus(): Promise<{ needs_setup: boolean }> {
  try {
    return await api<{ needs_setup: boolean }>("/auth/setup/status/");
  } catch {
    return { needs_setup: false };
  }
}

/** First-run only: create the initial SUPERADMIN. On success the session is
 *  already signed in, so route straight to MFA enrolment. */
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

/* --------------------------------------------------------- staff admin */

export interface DirectoryUser {
  id: string;
  username: string;
  email: string;
  role: Role;
  is_active: boolean;
  status: string;
  display_name: string;
}

export function listUsers(): Promise<DirectoryUser[]> {
  return api<DirectoryUser[]>("/auth/users/");
}

export interface StaffInvite {
  token: string;
  email: string;
  role: string;
  expires_at: string;
}

export async function inviteStaff(
  email: string,
  role: string,
): Promise<StaffInvite> {
  await ensureCsrf();
  return api<StaffInvite>("/auth/invite/", {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
}

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
