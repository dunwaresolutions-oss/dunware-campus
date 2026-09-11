import { api } from "./api";
import { create, list } from "./resource";

export type StaffAudience = "DIRECT" | "TEACHERS" | "TUTORS" | "ALL_STAFF";

export interface StaffMessage {
  id: string;
  sender: string | null;
  sender_name: string;
  recipient: string | null;
  recipient_name: string;
  audience: StaffAudience;
  body: string;
  urgent: boolean;
  created_at: string;
}

/** Newest first (server ordering) — the inbox panel shows these as-is. */
export const listStaffMessages = () => list<StaffMessage>("staff-messages");

export const sendStaffMessage = (input: {
  recipient?: string | null;
  audience: StaffAudience;
  body: string;
  urgent?: boolean;
}) => create<StaffMessage>("staff-messages", input);

export const unreadStaffMessageCount = () =>
  api<{ unread: number }>("/staff-messages/unread_count/");

export const markStaffMessagesRead = () =>
  api<{ unread: number }>("/staff-messages/mark_read/", { method: "POST" });
