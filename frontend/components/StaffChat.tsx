"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { whoami, type Role } from "@/lib/auth";
import { useAll } from "@/lib/hooks";
import { useToast } from "@/components/Toast";
import { apiMessage } from "@/lib/format";
import {
  deleteStaffMessage,
  listStaffMessages,
  markStaffMessagesRead,
  sendStaffMessage,
  unreadStaffMessageCount,
  type StaffAudience,
  type StaffMessage,
} from "@/lib/staffchat";

const OFFICE: Role[] = ["SUPERADMIN", "ADMIN", "FRONT_DESK"];

const AUDIENCE_LABEL: Record<StaffAudience, string> = {
  DIRECT: "Direct message",
  TEACHERS: "All teachers",
  TUTORS: "All tutors",
  ALL_STAFF: "All staff",
};

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.round(ms / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return new Date(iso).toLocaleString();
}

/**
 * Intranet-only staff chat/alert bell — direct messages between any two
 * staff accounts, plus role broadcasts (teachers / tutors / all staff)
 * restricted to front office. Never rendered inside the parent/student
 * portal layout, so it is unreachable from there regardless.
 *
 * Poller-only: an "unread" badge refreshes every 15s always; the message
 * list only while the panel is open. No websockets, matching the rest of
 * the app's no-persistent-connection deployment (WSGI + waitress, no Redis).
 */
export function StaffChat() {
  const qc = useQueryClient();
  const toast = useToast();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const [recipient, setRecipient] = useState("");
  const [audience, setAudience] = useState<StaffAudience>("DIRECT");
  const [body, setBody] = useState("");
  const [urgent, setUrgent] = useState(false);

  // The bell lives inside the sidebar, which is its own stacking context
  // (position: sticky) that always paints *behind* the main content's own
  // stacking contexts (every glass/backdrop-blur Card creates one) further
  // down the DOM — no z-index inside the sidebar can out-rank that. Portal
  // the popover to <body> and position it with fixed coordinates instead of
  // relying on being a positioned descendant of the bell.
  useEffect(() => {
    if (!open) return;
    const place = () => {
      const r = buttonRef.current?.getBoundingClientRect();
      if (r) setPos({ top: r.bottom + 6, left: r.left });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);

  const { data: me } = useQuery({ queryKey: ["me"], queryFn: whoami });
  const canBroadcast = !!me?.role && OFFICE.includes(me.role);

  const { data: unread } = useQuery({
    queryKey: ["staffchat", "unread"],
    queryFn: unreadStaffMessageCount,
    refetchInterval: 15_000,
  });

  const { data: page } = useQuery({
    queryKey: ["staffchat", "messages"],
    queryFn: listStaffMessages,
    enabled: open,
    refetchInterval: open ? 8_000 : false,
  });
  const messages: StaffMessage[] = page?.results ?? [];

  const staff = useAll<{ id: string; display_name: string; role: Role }>(
    "auth/users",
    undefined,
    open,
  );
  const recipients = (staff.data ?? []).filter(
    (u) => u.id !== me?.id && u.role !== "PARENT" && u.role !== "STUDENT",
  );

  const markRead = useMutation({
    mutationFn: markStaffMessagesRead,
    onSuccess: () => qc.setQueryData(["staffchat", "unread"], { unread: 0 }),
  });

  useEffect(() => {
    if (open && (unread?.unread ?? 0) > 0) markRead.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const send = useMutation({
    mutationFn: sendStaffMessage,
    onSuccess: () => {
      setBody("");
      setUrgent(false);
      qc.invalidateQueries({ queryKey: ["staffchat"] });
    },
    onError: (err) => toast("error", apiMessage(err)),
  });

  const del = useMutation({
    mutationFn: deleteStaffMessage,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["staffchat", "messages"] }),
    onError: (err) => toast("error", apiMessage(err)),
  });

  // Mirrors the server's own rule (views.py _can_delete) so the button only
  // shows where the request would actually succeed: front office can clear
  // anything; anyone else only their own sent message, or a direct message
  // sent to them -- not a broadcast they merely received.
  function canDelete(m: StaffMessage): boolean {
    if (canBroadcast) return true;
    if (m.sender === me?.id) return true;
    return m.audience === "DIRECT" && m.recipient === me?.id;
  }

  const canSend = useMemo(() => {
    if (!body.trim()) return false;
    if (audience === "DIRECT") return !!recipient;
    return canBroadcast;
  }, [body, audience, recipient, canBroadcast]);

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        onClick={() => setOpen((v) => !v)}
        className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] text-[var(--campus-muted)] transition-colors hover:border-[var(--campus-accent)] hover:text-[var(--campus-fg)]"
        title="Staff chat"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path
            d="M4 5h16v10a2 2 0 0 1-2 2H9l-4 3v-3H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        {!!unread?.unread && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold leading-none text-white">
            {unread.unread > 99 ? "99+" : unread.unread}
          </span>
        )}
      </button>

      {open && pos && createPortal(
        <>
          <div className="fixed inset-0 z-[90]" onClick={() => setOpen(false)} />
          <div
            style={{
              top: pos.top,
              left: Math.min(pos.left, window.innerWidth - 380 - 12),
            }}
            className="campus-modal-panel fixed z-[91] flex max-h-[70vh] w-[380px] flex-col overflow-hidden rounded-xl border border-[var(--campus-line)] bg-[var(--campus-input-bg)] shadow-[var(--campus-shadow-lg)]"
          >
            <div className="border-b border-[var(--campus-line)] px-3.5 py-2.5 text-sm font-semibold">
              Staff chat
              <span className="ml-1.5 font-normal text-[var(--campus-muted)]">
                — intranet only, not visible to portals
              </span>
            </div>

            <div className="flex-1 space-y-2 overflow-y-auto px-3.5 py-2.5">
              {messages.length === 0 && (
                <p className="py-6 text-center text-xs text-[var(--campus-muted)]">
                  No messages yet.
                </p>
              )}
              {messages.map((m) => {
                const mine = m.sender === me?.id;
                return (
                  <div
                    key={m.id}
                    className={`rounded-lg border px-2.5 py-1.5 text-xs ${
                      m.urgent
                        ? "border-red-400/50 bg-red-500/10"
                        : "border-[var(--campus-line)] bg-[var(--campus-input-bg)]"
                    }`}
                  >
                    <div className="mb-0.5 flex items-center justify-between gap-2 text-[11px] text-[var(--campus-muted)]">
                      <span className="font-medium text-[var(--campus-fg)]">
                        {mine ? "You" : m.sender_name}
                        {m.audience !== "DIRECT" && ` → ${AUDIENCE_LABEL[m.audience]}`}
                        {m.audience === "DIRECT" && !mine && m.recipient_name
                          ? ` → ${m.recipient_name}`
                          : ""}
                        {m.urgent && (
                          <span className="ml-1 font-semibold text-red-500">URGENT</span>
                        )}
                      </span>
                      <span className="flex shrink-0 items-center gap-1.5">
                        {timeAgo(m.created_at)}
                        {canDelete(m) && (
                          <button
                            onClick={() => del.mutate(m.id)}
                            disabled={del.isPending}
                            title="Remove this message"
                            className="text-[var(--campus-muted)] hover:text-red-500 disabled:opacity-40"
                          >
                            ✕
                          </button>
                        )}
                      </span>
                    </div>
                    <div className="whitespace-pre-wrap text-[var(--campus-fg)]">{m.body}</div>
                  </div>
                );
              })}
            </div>

            <div className="space-y-2 border-t border-[var(--campus-line)] px-3.5 py-2.5">
              <div className="flex gap-1.5">
                <select
                  value={audience}
                  onChange={(e) => {
                    setAudience(e.target.value as StaffAudience);
                    setRecipient("");
                  }}
                  className="flex-1 rounded-md border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-2 py-1.5 text-xs"
                >
                  <option value="DIRECT">Direct message</option>
                  {canBroadcast && (
                    <>
                      <option value="TEACHERS">All teachers</option>
                      <option value="TUTORS">All tutors</option>
                      <option value="ALL_STAFF">All staff</option>
                    </>
                  )}
                </select>
                {audience === "DIRECT" && (
                  <select
                    value={recipient}
                    onChange={(e) => setRecipient(e.target.value)}
                    className="flex-1 rounded-md border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-2 py-1.5 text-xs"
                  >
                    <option value="">To…</option>
                    {recipients.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.display_name}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder={
                  audience === "DIRECT"
                    ? "Message…"
                    : `Broadcast to ${AUDIENCE_LABEL[audience].toLowerCase()}…`
                }
                rows={2}
                className="w-full resize-none rounded-md border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-2 py-1.5 text-xs focus:outline-none"
              />
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-1.5 text-[11px] text-[var(--campus-muted)]">
                  <input
                    type="checkbox"
                    checked={urgent}
                    onChange={(e) => setUrgent(e.target.checked)}
                  />
                  Urgent (e.g. safety, needs immediate attention)
                </label>
                <button
                  disabled={!canSend || send.isPending}
                  onClick={() =>
                    send.mutate({
                      recipient: audience === "DIRECT" ? recipient : null,
                      audience,
                      body: body.trim(),
                      urgent,
                    })
                  }
                  className="rounded-md bg-[var(--campus-accent)] px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-[var(--campus-accent-strong)] disabled:opacity-40"
                >
                  Send
                </button>
              </div>
            </div>
          </div>
        </>,
        document.body,
      )}
    </div>
  );
}
