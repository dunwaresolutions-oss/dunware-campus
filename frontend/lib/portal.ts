import { api, ensureCsrf } from "./api";

/** The consolidated parent / student "my world" payload. */
export interface PortalDashboard {
  children: PortalChild[];
  announcements: PortalAnnouncement[];
  message_threads: PortalThreadSummary[];
  contact_change_requests: ContactChangeRequest[];
}

/** A read-only invoice summary — no card data ever appears here. */
export interface PortalInvoice {
  id: string;
  status: "ISSUED" | "PARTIALLY_PAID" | "PAID" | "OVERDUE" | "VOID";
  total_cents: number;
  balance_cents: number;
  due_date: string | null;
}

export interface PortalChild {
  id: string;
  display_name: string;
  student_number: string;
  primary_group_id: string | null;
  upcoming_sessions: Array<{
    id: string;
    group_id: string;
    date: string;
    start_time: string;
    end_time: string;
    title: string;
  }>;
  recent_attendance: Array<{
    id: string;
    date: string;
    status: string;
    checked_in_at: string | null;
    checked_out_at: string | null;
  }>;
  released_report_cards: Array<{ id: string; term_id: string; released_at: string }>;
  upcoming_bookings: Array<{
    id: string;
    offering: string;
    starts_at: string;
    status: string;
  }>;
  open_incidents: Array<{ id: string; occurred_at: string; category: string }>;
  pending_consents: string[];
  invoices: PortalInvoice[]; // billing is the only writer — read-only here
}

export interface PortalAnnouncement {
  id: string;
  title: string;
  body: string;
  published_at: string;
  pinned: boolean;
}

export interface PortalThreadSummary {
  id: string;
  subject: string;
  closed: boolean;
  last_message_at: string | null;
  message_count: number;
}

export interface ContactChangeRequest {
  id: string;
  field: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  proposed_value?: string;
  reason?: string;
  created_at: string;
}

export function portalDashboard(): Promise<PortalDashboard> {
  return api<PortalDashboard>("/portal/dashboard/");
}

/** Propose a change to your own contact details — staff approve or reject it. */
export async function requestContactChange(input: {
  field: "email" | "phone" | "address" | "receives_communications" | "lives_with";
  proposed_value: string;
  reason?: string;
  student?: string;
}): Promise<ContactChangeRequest> {
  await ensureCsrf();
  return api<ContactChangeRequest>("/portal/contact-change-requests/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

/** Record a consent decision — always a new versioned row, never an edit. */
export async function submitConsent(input: {
  student: string;
  kind: string;
  granted: boolean;
  version?: string;
  note?: string;
}): Promise<{ id: string; kind: string; granted: boolean; version: string }> {
  await ensureCsrf();
  return api("/portal/consents/", { method: "POST", body: JSON.stringify(input) });
}
