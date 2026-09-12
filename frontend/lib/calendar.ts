import { api } from "./api";

export interface CalendarSession {
  id: number;
  group: string;
  group_name?: string;
  room_name?: string;
  staff_name?: string;
  date: string; // YYYY-MM-DD
  start_time: string; // HH:MM[:SS]
  end_time: string;
  title: string;
  status: "SCHEDULED" | "CANCELLED";
  cancelled_reason?: string;
  /** HH:MM if this session runs past a same-day early dismissal, else null. */
  early_dismissal_time?: string | null;
}

export interface CalendarClosure {
  id: string;
  start_date: string;
  end_date: string;
  reason: string;
  group: string | null;
  group_name: string | null;
}

export interface CalendarEarlyDismissal {
  id: string;
  date: string;
  dismissal_time: string; // HH:MM
  reason: string;
  group: string | null;
  group_name: string | null;
}

export interface CalendarPayload {
  from: string;
  to: string;
  sessions: CalendarSession[];
  closures: CalendarClosure[];
  early_dismissals: CalendarEarlyDismissal[];
}

export const fetchCalendar = (
  from: string,
  to: string,
  groupId?: string,
  studentId?: string,
): Promise<CalendarPayload> => {
  const q = new URLSearchParams({ from, to });
  // a student filter means "her whole timetable" - every group she's
  // enrolled in - so it takes precedence over a single group pick.
  if (studentId) q.set("student", studentId);
  else if (groupId) q.set("group", groupId);
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
