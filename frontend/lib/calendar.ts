import { api } from "./api";

export interface CalendarSession {
  id: number;
  group: number;
  group_name?: string;
  room_name?: string;
  staff_name?: string;
  date: string; // YYYY-MM-DD
  start_time: string; // HH:MM[:SS]
  end_time: string;
  title: string;
  status: "SCHEDULED" | "CANCELLED";
  cancelled_reason?: string;
}

export interface CalendarClosure {
  id: string;
  start_date: string;
  end_date: string;
  reason: string;
  group: number | null;
  group_name: string | null;
}

export interface CalendarPayload {
  from: string;
  to: string;
  sessions: CalendarSession[];
  closures: CalendarClosure[];
}

export const fetchCalendar = (
  from: string,
  to: string,
  groupId?: number | "",
): Promise<CalendarPayload> => {
  const q = new URLSearchParams({ from, to });
  if (groupId) q.set("group", String(groupId));
  return api<CalendarPayload>(`/sessions/calendar/?${q.toString()}`);
};

/* ---- date helpers (local time, no external dep) ---------------------- */

export const iso = (d: Date): string => {
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 60_000);
  return z.toISOString().slice(0, 10);
};

export const addDays = (d: Date, n: number): Date => {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
};

/** Monday-based start of week. */
export const startOfWeek = (d: Date): Date => {
  const x = new Date(d);
  const dow = (x.getDay() + 6) % 7; // Mon=0 … Sun=6
  x.setHours(0, 0, 0, 0);
  return addDays(x, -dow);
};

export const startOfMonthGrid = (d: Date): Date =>
  startOfWeek(new Date(d.getFullYear(), d.getMonth(), 1));

export const minutesOf = (hhmm: string): number => {
  const m = /^(\d{2}):(\d{2})/.exec(hhmm);
  return m ? +m[1] * 60 + +m[2] : 0;
};
