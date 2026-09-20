import { api, ensureCsrf } from "./api";
import { actList } from "./resource";

/** The consolidated parent / student "my world" payload. */
export interface PortalDashboard {
  collects_fees: boolean;
  currency: string;
  children: PortalChild[];
  announcements: PortalAnnouncement[];
  message_threads: PortalThreadSummary[];
  contact_change_requests: ContactChangeRequest[];
}

/** A read-only invoice summary — no card data ever appears here. */
export interface PortalInvoice {
  id: string;
  status: "ISSUED" | "PARTIALLY_PAID" | "PAID" | "OVERDUE" | "VOID";
  currency: string;
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
  ieps: Array<{
    id: string;
    school_year: string;
    status: string;
    primary_concern: string;
    review_date: string | null;
    goals: Array<{ area: string; progress: string }>;
  }>;
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

/** One invoice's slice of a checkout — a combined family payment has one
 * of these per child; a single-invoice payment still has exactly one. */
export interface PaymentAllocation {
  invoice: string;
  invoice_number: string;
  student_name: string;
  allocated_cents: number;
}

export interface PaymentAttempt {
  id: string;
  allocations: PaymentAllocation[];
  gateway: string;
  reference: string;
  amount_cents: number;
  currency: string;
  status: "INITIALIZED" | "PENDING" | "SUCCESS" | "FAILED" | "ABANDONED" | "MISMATCH";
  checkout_url: string;
  channel: string;
  created_at: string;
  updated_at: string;
}

/** Start a hosted checkout for one or several invoices at once — a family
 * combining two or more children's invoices into a single real charge.
 * `amount_cents` lets the payer enter a total smaller than the combined
 * balance (partial payment); omitted, the full combined balance is charged.
 * The gateway itself sends the receipt email — Campus never does. */
export async function payInvoices(input: {
  invoice_ids: string[];
  amount_cents?: number;
  return_url?: string;
}): Promise<PaymentAttempt> {
  await ensureCsrf();
  return actList<PaymentAttempt>("invoices", "pay", input);
}

/** Live-resolves against the gateway on the backend (P3's on-demand
 * confirmation path) — polling this is how the return page knows when a
 * checkout has actually settled. */
export function getPaymentAttempt(reference: string): Promise<PaymentAttempt> {
  return api<PaymentAttempt>(`/payment-attempts/${encodeURIComponent(reference)}/`);
}
