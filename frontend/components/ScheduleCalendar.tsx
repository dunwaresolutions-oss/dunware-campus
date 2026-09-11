"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  addDays,
  fetchCalendar,
  iso,
  minutesOf,
  startOfMonthGrid,
  startOfWeek,
  type CalendarClosure,
  type CalendarEarlyDismissal,
  type CalendarSession,
} from "@/lib/calendar";
import { Spinner, ErrorNote } from "@/components/ui";
import { apiMessage, time } from "@/lib/format";

type View = "month" | "week" | "day";
const DAY_START = 7;
const DAY_END = 19;
const PX_PER_MIN = 44 / 60;
const WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const sameDay = (a: Date, b: Date) =>
  a.getFullYear() === b.getFullYear() &&
  a.getMonth() === b.getMonth() &&
  a.getDate() === b.getDate();

function rangeFor(view: View, anchor: Date): [Date, Date] {
  if (view === "day") return [anchor, anchor];
  if (view === "week") {
    const s = startOfWeek(anchor);
    return [s, addDays(s, 6)];
  }
  const s = startOfMonthGrid(anchor);
  return [s, addDays(s, 41)];
}

function titleFor(view: View, anchor: Date): string {
  if (view === "day")
    return anchor.toLocaleDateString(undefined, {
      weekday: "long",
      month: "long",
      day: "numeric",
      year: "numeric",
    });
  if (view === "week") {
    const s = startOfWeek(anchor);
    const e = addDays(s, 6);
    const sm = s.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    const em = e.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
    return `${sm} – ${em}`;
  }
  return anchor.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

function closureOn(day: Date, closures: CalendarClosure[]): CalendarClosure | null {
  const d = iso(day);
  return closures.find((c) => c.start_date <= d && d <= c.end_date) ?? null;
}

function earlyDismissalOn(
  day: Date,
  dismissals: CalendarEarlyDismissal[],
): CalendarEarlyDismissal | null {
  const d = iso(day);
  return dismissals.find((e) => e.date === d) ?? null;
}

/* lane-pack overlapping sessions in one column */
function withLanes(items: CalendarSession[]) {
  const sorted = [...items].sort(
    (a, b) => minutesOf(a.start_time) - minutesOf(b.start_time),
  );
  const laneEnds: number[] = [];
  const placed = sorted.map((s) => {
    const start = minutesOf(s.start_time);
    const end = Math.max(minutesOf(s.end_time), start + 15);
    let lane = laneEnds.findIndex((e) => e <= start);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(end);
    } else {
      laneEnds[lane] = end;
    }
    return { s, start, end, lane };
  });
  const lanes = Math.max(1, laneEnds.length);
  return { placed, lanes };
}

export function ScheduleCalendar({
  groups,
  onOpenSession,
  fixedGroupId,
  initialView = "month",
}: {
  groups: { id: string; name: string }[];
  onOpenSession: (s: CalendarSession) => void;
  /** Lock to one group and hide the filter — e.g. a student's own timetable. */
  fixedGroupId?: string;
  initialView?: View;
}) {
  const [view, setView] = useState<View>(initialView);
  const [anchor, setAnchor] = useState(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  });
  const [pickedGroupId, setPickedGroupId] = useState<string>("");
  const groupId = fixedGroupId ?? pickedGroupId;

  const [from, to] = rangeFor(view, anchor);
  const q = useQuery({
    queryKey: ["calendar", view === "month" ? "m" : view, iso(from), iso(to), groupId],
    queryFn: () => fetchCalendar(iso(from), iso(to), groupId),
  });

  const byDay = useMemo(() => {
    const map = new Map<string, CalendarSession[]>();
    for (const s of q.data?.sessions ?? []) {
      const arr = map.get(s.date) ?? [];
      arr.push(s);
      map.set(s.date, arr);
    }
    return map;
  }, [q.data]);
  const closures = q.data?.closures ?? [];
  const earlyDismissals = q.data?.early_dismissals ?? [];

  const step = view === "month" ? "month" : view === "week" ? 7 : 1;
  const nav = (dir: -1 | 0 | 1) => {
    if (dir === 0) {
      const d = new Date();
      d.setHours(0, 0, 0, 0);
      setAnchor(d);
      return;
    }
    if (step === "month") {
      setAnchor(new Date(anchor.getFullYear(), anchor.getMonth() + dir, 1));
    } else {
      setAnchor(addDays(anchor, dir * step));
    }
  };

  return (
    <div>
      {/* toolbar */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex overflow-hidden rounded-lg border border-[var(--campus-line)]">
          {(["month", "week", "day"] as View[]).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                view === v
                  ? "bg-[var(--campus-accent)] text-white"
                  : "bg-[var(--campus-input-bg)] text-[var(--campus-fg)] hover:bg-black/5 dark:hover:bg-white/10"
              }`}
            >
              {v}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={() => nav(-1)}
            className="grid h-7 w-7 place-items-center rounded-md border border-[var(--campus-line)] text-sm hover:border-[var(--campus-accent)]"
            aria-label="Previous"
          >
            ‹
          </button>
          <button
            onClick={() => nav(0)}
            className="rounded-md border border-[var(--campus-line)] px-2.5 py-1 text-xs hover:border-[var(--campus-accent)]"
          >
            Today
          </button>
          <button
            onClick={() => nav(1)}
            className="grid h-7 w-7 place-items-center rounded-md border border-[var(--campus-line)] text-sm hover:border-[var(--campus-accent)]"
            aria-label="Next"
          >
            ›
          </button>
        </div>

        <div className="text-sm font-semibold">{titleFor(view, anchor)}</div>

        {!fixedGroupId && (
          <select
            value={pickedGroupId}
            onChange={(e) => setPickedGroupId(e.target.value)}
            className="ml-auto rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-2.5 py-1.5 text-xs"
          >
            <option value="">All groups</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {q.isLoading ? (
        <Spinner />
      ) : q.isError ? (
        <ErrorNote message={apiMessage(q.error)} />
      ) : view === "month" ? (
        <MonthGrid
          from={from}
          anchorMonth={anchor.getMonth()}
          byDay={byDay}
          closures={closures}
          earlyDismissals={earlyDismissals}
          onOpenSession={onOpenSession}
          onPickDay={(d) => {
            setAnchor(d);
            setView("day");
          }}
        />
      ) : (
        <TimeGrid
          days={
            view === "week"
              ? Array.from({ length: 7 }, (_, i) => addDays(startOfWeek(anchor), i))
              : [anchor]
          }
          byDay={byDay}
          closures={closures}
          earlyDismissals={earlyDismissals}
          onOpenSession={onOpenSession}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------- month ---- */

function MonthGrid({
  from,
  anchorMonth,
  byDay,
  closures,
  earlyDismissals,
  onOpenSession,
  onPickDay,
}: {
  from: Date;
  anchorMonth: number;
  byDay: Map<string, CalendarSession[]>;
  closures: CalendarClosure[];
  earlyDismissals: CalendarEarlyDismissal[];
  onOpenSession: (s: CalendarSession) => void;
  onPickDay: (d: Date) => void;
}) {
  const today = new Date();
  const days = Array.from({ length: 42 }, (_, i) => addDays(from, i));
  return (
    <div className="overflow-hidden rounded-xl border border-[var(--campus-line)]">
      <div className="grid grid-cols-7 border-b border-[var(--campus-line)] bg-[var(--campus-input-bg)] text-[11px] font-medium text-[var(--campus-muted)]">
        {WD.map((d) => (
          <div key={d} className="px-2 py-1.5 text-center">
            {d}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {days.map((d, i) => {
          const list = byDay.get(iso(d)) ?? [];
          const cl = closureOn(d, closures);
          const ed = earlyDismissalOn(d, earlyDismissals);
          const out = d.getMonth() !== anchorMonth;
          const isToday = sameDay(d, today);
          return (
            <div
              key={i}
              className={`min-h-[104px] border-b border-r border-[var(--campus-line)] p-1.5 ${
                i % 7 === 6 ? "border-r-0" : ""
              } ${out ? "bg-black/[0.015] dark:bg-white/[0.015]" : ""} ${
                cl
                  ? "bg-amber-50/60 dark:bg-amber-950/20"
                  : ed
                    ? "bg-sky-50/60 dark:bg-sky-950/20"
                    : ""
              }`}
            >
              <div className="flex items-center justify-between">
                <span
                  className={`grid h-5 min-w-5 place-items-center rounded-full px-1 text-[11px] ${
                    isToday
                      ? "bg-[var(--campus-accent)] font-semibold text-white"
                      : out
                        ? "text-[var(--campus-muted)]"
                        : ""
                  }`}
                >
                  {d.getDate()}
                </span>
                {cl && (
                  <span className="truncate text-[10px] text-amber-700 dark:text-amber-400">
                    {cl.reason}
                  </span>
                )}
                {!cl && ed && (
                  <span className="truncate text-[10px] text-sky-700 dark:text-sky-400">
                    Ends {time(ed.dismissal_time)}
                  </span>
                )}
              </div>
              <div className="mt-1 space-y-0.5">
                {list.slice(0, 3).map((s) => (
                  <Chip key={s.id} s={s} onClick={() => onOpenSession(s)} />
                ))}
                {list.length > 3 && (
                  <button
                    onClick={() => onPickDay(d)}
                    className="w-full rounded px-1 text-left text-[10px] text-[var(--campus-muted)] hover:text-[var(--campus-accent)]"
                  >
                    +{list.length - 3} more
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Chip({ s, onClick }: { s: CalendarSession; onClick: () => void }) {
  const cancelled = s.status === "CANCELLED";
  const early = !!s.early_dismissal_time;
  return (
    <button
      onClick={onClick}
      title={`${time(s.start_time)}–${time(s.end_time)} · ${s.group_name ?? ""}${
        s.room_name ? ` · ${s.room_name}` : ""
      }${early ? ` · early dismissal ${time(s.early_dismissal_time!)}` : ""}`}
      className={`block w-full truncate rounded px-1 py-0.5 text-left text-[10.5px] ${
        cancelled
          ? "text-[var(--campus-muted)] line-through"
          : early
            ? "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300"
            : "bg-[var(--campus-accent-soft)] text-[var(--campus-accent)]"
      }`}
    >
      <span className="tabular-nums">{time(s.start_time)}</span>{" "}
      {s.title || s.group_name || "Session"}
      {early && !cancelled && " ⏰"}
    </button>
  );
}

/* --------------------------------------------------------- week / day --- */

function TimeGrid({
  days,
  byDay,
  closures,
  earlyDismissals,
  onOpenSession,
}: {
  days: Date[];
  byDay: Map<string, CalendarSession[]>;
  closures: CalendarClosure[];
  earlyDismissals: CalendarEarlyDismissal[];
  onOpenSession: (s: CalendarSession) => void;
}) {
  const today = new Date();
  const hours = Array.from(
    { length: DAY_END - DAY_START },
    (_, i) => DAY_START + i,
  );
  const gridH = hours.length * 60 * PX_PER_MIN;

  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--campus-line)]">
      <div
        className="grid min-w-[560px]"
        style={{ gridTemplateColumns: `48px repeat(${days.length}, 1fr)` }}
      >
        {/* header */}
        <div className="border-b border-[var(--campus-line)] bg-[var(--campus-input-bg)]" />
        {days.map((d, i) => {
          const isToday = sameDay(d, today);
          return (
            <div
              key={i}
              className={`border-b border-l border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-2 py-1.5 text-center text-[11px] ${
                isToday ? "text-[var(--campus-accent)]" : "text-[var(--campus-muted)]"
              }`}
            >
              <div className="font-medium">{WD[(d.getDay() + 6) % 7]}</div>
              <div className={isToday ? "font-semibold" : ""}>
                {d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
              </div>
            </div>
          );
        })}

        {/* hour gutter */}
        <div className="relative" style={{ height: gridH }}>
          {hours.map((h) => (
            <div
              key={h}
              className="absolute right-1 -translate-y-1/2 text-[10px] text-[var(--campus-muted)] tabular-nums"
              style={{ top: (h - DAY_START) * 60 * PX_PER_MIN }}
            >
              {String(h).padStart(2, "0")}:00
            </div>
          ))}
        </div>

        {/* day columns */}
        {days.map((d, i) => {
          const list = byDay.get(iso(d)) ?? [];
          const cl = closureOn(d, closures);
          const ed = earlyDismissalOn(d, earlyDismissals);
          const { placed, lanes } = withLanes(list);
          const edTop = ed
            ? Math.max(0, (minutesOf(ed.dismissal_time) - DAY_START * 60) * PX_PER_MIN)
            : null;
          return (
            <div
              key={i}
              className={`relative border-l border-[var(--campus-line)] ${
                cl ? "bg-amber-50/50 dark:bg-amber-950/20" : ""
              }`}
              style={{ height: gridH }}
            >
              {hours.map((h) => (
                <div
                  key={h}
                  className="absolute inset-x-0 border-b border-[var(--campus-line)]/60"
                  style={{ top: (h - DAY_START) * 60 * PX_PER_MIN, height: 0 }}
                />
              ))}
              {cl && (
                <div className="absolute inset-x-1 top-1 truncate rounded bg-amber-100 px-1 py-0.5 text-[10px] text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                  {cl.reason}
                </div>
              )}
              {!cl && ed && edTop !== null && (
                <>
                  <div
                    className="absolute inset-x-1 truncate rounded bg-sky-100 px-1 py-0.5 text-[10px] text-sky-800 dark:bg-sky-900/40 dark:text-sky-300"
                    style={{ top: 1 }}
                  >
                    Early dismissal {time(ed.dismissal_time)} — {ed.reason}
                  </div>
                  <div
                    className="absolute inset-x-0 border-t-2 border-dashed border-sky-400/70"
                    style={{ top: edTop }}
                  />
                </>
              )}
              {placed.map(({ s, start, end, lane }) => {
                const top = Math.max(0, (start - DAY_START * 60) * PX_PER_MIN);
                const height = Math.max(16, (end - start) * PX_PER_MIN - 2);
                const cancelled = s.status === "CANCELLED";
                const early = !!s.early_dismissal_time;
                const w = 100 / lanes;
                return (
                  <button
                    key={s.id}
                    onClick={() => onOpenSession(s)}
                    style={{
                      top,
                      height,
                      left: `calc(${lane * w}% + 2px)`,
                      width: `calc(${w}% - 4px)`,
                    }}
                    className={`absolute overflow-hidden rounded-md border px-1.5 py-0.5 text-left text-[10.5px] leading-tight ${
                      cancelled
                        ? "border-[var(--campus-line)] bg-[var(--campus-input-bg)] text-[var(--campus-muted)] line-through"
                        : early
                          ? "border-sky-400/40 bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300"
                          : "border-[var(--campus-accent)]/30 bg-[var(--campus-accent-soft)] text-[var(--campus-accent)]"
                    }`}
                  >
                    <div className="font-medium">
                      {s.title || s.group_name || "Session"}
                      {early && !cancelled && " ⏰"}
                    </div>
                    <div className="tabular-nums opacity-80">
                      {time(s.start_time)}–{time(s.end_time)}
                    </div>
                    {early && !cancelled && (
                      <div className="opacity-80">
                        ends {time(s.early_dismissal_time!)}
                      </div>
                    )}
                    {s.room_name && (
                      <div className="truncate opacity-70">{s.room_name}</div>
                    )}
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
