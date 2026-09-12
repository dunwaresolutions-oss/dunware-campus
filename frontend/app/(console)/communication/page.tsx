"use client";

import { useEffect, useState } from "react";
import { useAll, useList, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { create, act, patch, retrieve } from "@/lib/resource";
import { PageHeader, Tabs, Badge, Button, Card, Spinner } from "@/components/ui";
import { Modal } from "@/components/Modal";
import { RecordForm } from "@/components/RecordForm";
import { MessageTemplates } from "@/components/MessageTemplates";
import { useToast } from "@/components/Toast";
import { datetime, date, apiMessage, label } from "@/lib/format";
import { searchStudents } from "@/lib/students";
import { useQueryClient } from "@tanstack/react-query";

interface AnnRow {
  id: number;
  title: string;
  body: string;
  audience: string;
  group: number | null;
  pinned: boolean;
  published_at: string | null;
  email_sent_at: string | null;
}
interface IncRow {
  id: number;
  student: string;
  student_name?: string;
  occurred_at: string;
  location: string;
  category: string;
  severity: number | null;
  description: string;
  action_taken: string;
  first_aid_given: boolean;
  status: string;
  guardians_notified_at: string | null;
  acknowledged_count?: number;
}

export default function CommunicationPage() {
  const [tab, setTab] = useState("threads");
  const [openAnn, setOpenAnn] = useState<AnnRow | null>(null);
  const [openInc, setOpenInc] = useState<IncRow | null>(null);
  const toast = useToast();
  const groups = useAll<{ id: number; name: string }>("groups");
  const groupOpts = options(groups.data, (g) => g.name);

  return (
    <div>
      <PageHeader
        title="Messages"
        subtitle="Announcements, staff ↔ parent threads, incident reports with per-guardian acknowledgement, the email templates Campus sends (with [[merge fields]]), and the outbound email log. Email only — no SMS."
      />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "threads", label: "Threads" },
          { key: "announcements", label: "Announcements" },
          { key: "incidents", label: "Incident reports" },
          { key: "templates", label: "Templates" },
          { key: "email", label: "Email log" },
        ]}
      />

      {tab === "templates" && <MessageTemplates />}

      {tab === "announcements" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            An <b>announcement</b> is a one-to-many notice. Choose an audience —
            all staff / all parents / one group / whole site — then <b>Publish</b>,
            which stamps it and emails everyone in the audience. Before Publish it
            is a draft only staff can see; there is no un-publish. Press{" "}
            <b>Open</b> to read the body and see the audience and send state.
          </p>
          <CrudPanel<AnnRow>
            resource="announcements"
            singular="announcement"
            onRowOpen={setOpenAnn}
            columns={[
              { header: "Title", cell: (r) => r.title },
              { header: "Audience", cell: (r) => label(r.audience) },
              { header: "Pinned", cell: (r) => (r.pinned ? "Yes" : "—") },
              {
                header: "Published",
                cell: (r) =>
                  r.published_at ? (
                    <Badge tone="green">{datetime(r.published_at)}</Badge>
                  ) : (
                    <Badge>Draft</Badge>
                  ),
              },
            ]}
            fields={[
              { name: "title", label: "Title", required: true },
              { name: "body", label: "Body", type: "textarea", required: true },
              {
                name: "audience",
                label: "Audience",
                type: "select",
                required: true,
                options: ["ALL_STAFF", "ALL_PARENTS", "GROUP", "WHOLE_SITE"].map(
                  (v) => ({ value: v, label: label(v) }),
                ),
              },
              { name: "group", label: "Group (for GROUP audience)", type: "select", options: groupOpts },
              { name: "pinned", label: "Pinned", type: "checkbox" },
            ]}
            extraRowActions={(row, reload) =>
              !row.published_at ? (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={async () => {
                    try {
                      await act("announcements", row.id, "publish");
                      toast("success", "Published & emailed");
                      reload();
                    } catch (e) {
                      toast("error", apiMessage(e));
                    }
                  }}
                >
                  Publish
                </Button>
              ) : null
            }
          />
        </>
      )}

      {tab === "threads" && <Threads />}

      {tab === "incidents" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            An <b>incident report</b> is a structured record of something that
            happened to a child. Description and action taken are encrypted at
            rest. It starts as <b>Draft</b>; <b>Notify guardians</b> emails every
            communications-guardian and moves it to <b>Sent</b>. Once every one of
            them has acknowledged it from the portal it flips itself to{" "}
            <b>Acknowledged</b>. Press <b>Open</b> to read it and see who has
            acknowledged.
          </p>
          <CrudPanel<IncRow>
            resource="incident-reports"
            singular="incident report"
            searchable
            searchPlaceholder="Search by student, location or category…"
            onRowOpen={setOpenInc}
            columns={[
              { header: "Student", cell: (r) => r.student_name || r.student },
              { header: "Category", cell: (r) => label(r.category) },
              {
                header: "Severity",
                cell: (r) => (r.severity ? `${r.severity}/5` : "—"),
              },
              { header: "When", cell: (r) => datetime(r.occurred_at) },
              {
                header: "Status",
                cell: (r) => (
                  <Badge
                    tone={
                      r.status === "ACKNOWLEDGED"
                        ? "green"
                        : r.status === "SENT"
                          ? "amber"
                          : "neutral"
                    }
                  >
                    {label(r.status)}
                  </Badge>
                ),
              },
            ]}
            fields={[
              {
                name: "student", label: "Student", type: "search-select", required: true,
                search: searchStudents, initialLabelKey: "student_name",
              },
              { name: "occurred_at", label: "When", type: "datetime", required: true },
              { name: "location", label: "Location" },
              {
                name: "category",
                label: "Category",
                type: "select",
                required: true,
                options: [
                  "INJURY",
                  "BEHAVIOUR",
                  "ILLNESS",
                  "ALLERGY",
                  "SAFEGUARDING",
                  "OTHER",
                ].map((v) => ({ value: v, label: label(v) })),
              },
              {
                name: "severity",
                label: "Severity (1 minor – 5 serious)",
                type: "select",
                options: [
                  { value: 1, label: "1 – minor" },
                  { value: 2, label: "2" },
                  { value: 3, label: "3 – moderate" },
                  { value: 4, label: "4" },
                  { value: 5, label: "5 – serious" },
                ],
              },
              { name: "first_aid_given", label: "First aid given", type: "checkbox" },
              { name: "description", label: "Description (encrypted)", type: "textarea", required: true },
              { name: "action_taken", label: "Action taken (encrypted)", type: "textarea" },
            ]}
            extraRowActions={(row, reload) =>
              row.status === "DRAFT" ? (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={async () => {
                    try {
                      await act("incident-reports", row.id, "notify");
                      toast("success", "Guardians notified");
                      reload();
                    } catch (e) {
                      toast("error", apiMessage(e));
                    }
                  }}
                >
                  Notify guardians
                </Button>
              ) : null
            }
          />
        </>
      )}

      {tab === "email" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            The <b>email log</b> records every message Campus sent — kind,
            subject, recipient count, time, and whether it failed. The body is
            never stored; this is a delivery record, not an archive.
          </p>
          <CrudPanel
            resource="outbound-emails"
            singular="email"
            canCreate={false}
            canEdit={false}
            canDelete={false}
            columns={[
              { header: "Sent", cell: (r) => datetime(r.sent_at as string) },
              { header: "Kind", cell: (r) => label(r.kind as string) },
              { header: "Subject", cell: (r) => r.subject as string },
              {
                header: "To",
                cell: (r) =>
                  Array.isArray(r.to)
                    ? (r.to as string[]).length + " recipient(s)"
                    : String(r.to ?? "—"),
              },
              {
                header: "Result",
                cell: (r) =>
                  r.error ? (
                    <Badge tone="red">error</Badge>
                  ) : (
                    <Badge tone="green">sent</Badge>
                  ),
              },
            ]}
            detailTitle={(r) => `Email — ${(r.subject as string) || "message"}`}
            detailFields={[
              { label: "Sent", value: (r) => datetime(r.sent_at as string) },
              { label: "Kind", value: (r) => label(r.kind as string) },
              { label: "Subject", value: (r) => (r.subject as string) || "—" },
              {
                label: "Result",
                value: (r) => (r.error ? "Failed" : "Sent"),
              },
              {
                label: "About",
                value: (r) =>
                  r.object_type
                    ? `${r.object_type}${r.object_id ? ` #${String(r.object_id).slice(0, 8)}` : ""}`
                    : "—",
              },
              {
                label: "Recipients",
                long: true,
                value: (r) =>
                  Array.isArray(r.to) && (r.to as string[]).length
                    ? (r.to as string[]).join("\n")
                    : String(r.to ?? "—"),
              },
              {
                label: "Error",
                long: true,
                value: (r) => (r.error as string) || "—",
              },
            ]}
          />
        </>
      )}

      <AnnouncementDrawer
        ann={openAnn}
        onClose={() => setOpenAnn(null)}
        groupName={
          groups.data?.find((g) => g.id === openAnn?.group)?.name ?? ""
        }
      />
      <IncidentDrawer
        inc={openInc}
        onClose={() => setOpenInc(null)}
        studentName={openInc?.student_name || openInc?.student || ""}
      />
    </div>
  );
}

/* --------------------------------------------------- announcement drawer */

function AnnouncementDrawer({
  ann,
  onClose,
  groupName,
}: {
  ann: AnnRow | null;
  onClose: () => void;
  groupName: string;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [live, setLive] = useState<AnnRow | null>(ann);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    setLive(ann);
    setBody(ann?.body ?? "");
  }, [ann]);

  if (!ann || !live) return null;

  const published = !!live.published_at;

  async function refresh() {
    if (!ann) return;
    const fresh = await retrieve<AnnRow>("announcements", ann.id);
    setLive(fresh);
    setBody(fresh.body ?? "");
    qc.invalidateQueries({ queryKey: ["list", "announcements"] });
  }

  async function withBusy(key: string, fn: () => Promise<void>) {
    setBusy(key);
    try {
      await fn();
    } catch (e) {
      toast("error", apiMessage(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Modal open={!!ann} onClose={onClose} title={`Announcement — ${live.title}`} wide>
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          {published ? (
            <Badge tone="green">Published {datetime(live.published_at)}</Badge>
          ) : (
            <Badge>Draft</Badge>
          )}
          <span className="text-[var(--campus-muted)]">
            Audience: {label(live.audience)}
            {live.audience === "GROUP" && groupName ? ` — ${groupName}` : ""}
          </span>
          {live.pinned && <span className="text-[var(--campus-muted)]">Pinned</span>}
          {live.email_sent_at && (
            <span className="text-[var(--campus-muted)]">
              emailed {datetime(live.email_sent_at)}
            </span>
          )}
        </div>

        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
            Body
          </h3>
          <textarea
            className="w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm text-[var(--campus-fg)]"
            rows={8}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <div className="mt-1 flex justify-end">
            <Button
              size="sm"
              variant="subtle"
              disabled={busy === "body" || body === (live.body ?? "")}
              onClick={() =>
                withBusy("body", async () => {
                  await patch("announcements", ann.id, { body });
                  toast("success", "Saved");
                  await refresh();
                })
              }
            >
              {busy === "body" ? "Saving…" : "Save body"}
            </Button>
          </div>
        </section>

        <div className="flex items-center justify-between border-t border-[var(--campus-line)] pt-3">
          <p className="text-xs text-[var(--campus-muted)]">
            {published
              ? "Published. Editing the body here will not re-send the email."
              : "Publishing stamps it and emails the whole audience. There is no un-publish."}
          </p>
          {!published && (
            <Button
              disabled={busy === "publish"}
              onClick={() =>
                withBusy("publish", async () => {
                  await act("announcements", ann.id, "publish");
                  toast("success", "Published & emailed");
                  await refresh();
                })
              }
            >
              Publish
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}

/* ------------------------------------------------------- incident drawer */

function IncidentDrawer({
  inc,
  onClose,
  studentName,
}: {
  inc: IncRow | null;
  onClose: () => void;
  studentName: string;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [live, setLive] = useState<IncRow | null>(inc);
  const [description, setDescription] = useState("");
  const [actionTaken, setActionTaken] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const acks = useAll<{
    id: string;
    incident: number;
    guardian: number | null;
    signature_name: string;
    note: string;
    created_at: string;
  }>("incident-acknowledgements");

  useEffect(() => {
    setLive(inc);
    setDescription(inc?.description ?? "");
    setActionTaken(inc?.action_taken ?? "");
  }, [inc]);

  if (!inc || !live) return null;

  const mineAcks = (acks.data ?? []).filter((a) => a.incident === inc.id);
  const dirty =
    description !== (live.description ?? "") ||
    actionTaken !== (live.action_taken ?? "");

  async function refresh() {
    if (!inc) return;
    const fresh = await retrieve<IncRow>("incident-reports", inc.id);
    setLive(fresh);
    setDescription(fresh.description ?? "");
    setActionTaken(fresh.action_taken ?? "");
    qc.invalidateQueries({ queryKey: ["list", "incident-reports"] });
    qc.invalidateQueries({ queryKey: ["all", "incident-acknowledgements"] });
  }

  async function withBusy(key: string, fn: () => Promise<void>) {
    setBusy(key);
    try {
      await fn();
    } catch (e) {
      toast("error", apiMessage(e));
    } finally {
      setBusy(null);
    }
  }

  const box =
    "w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm text-[var(--campus-fg)]";

  return (
    <Modal
      open={!!inc}
      onClose={onClose}
      title={`Incident — ${studentName}`}
      wide
    >
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Badge
            tone={
              live.status === "ACKNOWLEDGED"
                ? "green"
                : live.status === "SENT"
                  ? "amber"
                  : "neutral"
            }
          >
            {label(live.status)}
          </Badge>
          <span className="text-[var(--campus-muted)]">{datetime(live.occurred_at)}</span>
          <span className="text-[var(--campus-muted)]">{label(live.category)}</span>
          {live.severity && (
            <span className="text-[var(--campus-muted)]">severity {live.severity}/5</span>
          )}
          {live.location && (
            <span className="text-[var(--campus-muted)]">at {live.location}</span>
          )}
          {live.first_aid_given && (
            <span className="text-[var(--campus-muted)]">first aid given</span>
          )}
        </div>

        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
            What happened <span className="normal-case font-normal">(encrypted)</span>
          </h3>
          <textarea
            className={box}
            rows={5}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </section>
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
            Action taken <span className="normal-case font-normal">(encrypted)</span>
          </h3>
          <textarea
            className={box}
            rows={4}
            value={actionTaken}
            onChange={(e) => setActionTaken(e.target.value)}
          />
        </section>
        <div className="flex justify-end">
          <Button
            size="sm"
            variant="subtle"
            disabled={!dirty || busy === "save"}
            onClick={() =>
              withBusy("save", async () => {
                await patch("incident-reports", inc.id, {
                  description,
                  action_taken: actionTaken,
                });
                toast("success", "Saved");
                await refresh();
              })
            }
          >
            {busy === "save" ? "Saving…" : "Save changes"}
          </Button>
        </div>

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
            Guardian acknowledgements ({mineAcks.length})
          </h3>
          {acks.isLoading ? (
            <Spinner />
          ) : mineAcks.length === 0 ? (
            <p className="text-sm text-[var(--campus-muted)]">
              {live.guardians_notified_at
                ? `Notified ${datetime(live.guardians_notified_at)}. No guardian has acknowledged yet.`
                : "Not notified yet — use Notify guardians below."}
            </p>
          ) : (
            <ul className="divide-y divide-[var(--campus-line)] rounded-md border border-[var(--campus-line)] text-sm">
              {mineAcks.map((a) => (
                <li
                  key={a.id}
                  className="flex items-center justify-between gap-2 px-3 py-2"
                >
                  <span>
                    {a.signature_name || `guardian #${a.guardian ?? "?"}`}
                    {a.note ? (
                      <span className="text-[var(--campus-muted)]"> — {a.note}</span>
                    ) : null}
                  </span>
                  <span className="text-xs text-[var(--campus-muted)]">
                    {date(a.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {live.status === "DRAFT" && (
          <div className="flex justify-end border-t border-[var(--campus-line)] pt-3">
            <Button
              disabled={busy === "notify"}
              onClick={() =>
                withBusy("notify", async () => {
                  await act("incident-reports", inc.id, "notify");
                  toast("success", "Guardians notified");
                  await refresh();
                })
              }
            >
              Notify guardians
            </Button>
          </div>
        )}
      </div>
    </Modal>
  );
}

interface ThreadRow {
  id: string;
  subject: string;
  student: string | null;
  closed: boolean;
  message_count?: number;
  last_message_at: string | null;
}

function Threads() {
  const qc = useQueryClient();
  const toast = useToast();
  const [openThread, setOpenThread] = useState<ThreadRow | null>(null);
  const [creating, setCreating] = useState(false);
  const threads = useList<ThreadRow>("message-threads");

  return (
    <>
      <p className="mb-3 text-sm text-[var(--campus-muted)]">
        A <b>thread</b> is a private staff ↔ parent conversation, optionally about
        one child. Only the participants (and admins) can read it; message bodies
        are encrypted at rest. Press <b>Open</b> to read the conversation and
        reply.
      </p>
      <Card>
        <div className="flex justify-end border-b border-[var(--campus-line)] p-3">
          <Button size="sm" onClick={() => setCreating(true)}>
            New thread
          </Button>
        </div>
        {threads.isLoading ? (
          <Spinner />
        ) : (
          <ul className="divide-y divide-[var(--campus-line)] text-sm">
            {(threads.data?.results ?? []).map((t) => (
              <li
                key={t.id}
                className="flex items-center justify-between gap-3 px-4 py-3"
              >
                <span className="min-w-0">
                  <span className="font-medium">{t.subject}</span>
                  <span className="block text-xs text-[var(--campus-muted)]">
                    {t.message_count ?? 0} msg · {datetime(t.last_message_at)}
                    {t.closed && " · closed"}
                  </span>
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setOpenThread(t)}
                >
                  Open
                </Button>
              </li>
            ))}
            {(threads.data?.results ?? []).length === 0 && (
              <li className="p-4 text-[var(--campus-muted)]">No threads yet.</li>
            )}
          </ul>
        )}

        <Modal
          open={creating}
          onClose={() => setCreating(false)}
          title="New message thread"
        >
          <RecordForm
            fields={[
              { name: "subject", label: "Subject", required: true },
              {
                name: "student", label: "About student (optional)", type: "search-select",
                search: searchStudents,
              },
            ]}
            submitLabel="Create thread"
            onSubmit={async (v) => {
              await create("message-threads", v);
              toast("success", "Thread created");
              setCreating(false);
              qc.invalidateQueries({ queryKey: ["list", "message-threads"] });
            }}
            onCancel={() => setCreating(false)}
          />
        </Modal>

        <Modal
          open={!!openThread}
          onClose={() => setOpenThread(null)}
          title={openThread ? openThread.subject : "Thread"}
          wide
        >
          {openThread && (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-3 text-sm text-[var(--campus-muted)]">
                <span>{openThread.message_count ?? 0} messages</span>
                <span>last activity {datetime(openThread.last_message_at)}</span>
                {openThread.closed && <span>· closed</span>}
              </div>
              <ThreadMessages threadId={openThread.id} />
            </div>
          )}
        </Modal>
      </Card>
    </>
  );
}

function ThreadMessages({ threadId }: { threadId: string }) {
  const qc = useQueryClient();
  const [body, setBody] = useState("");
  const msgs = useList<{ id: string; body: string; sender_name?: string; created_at: string }>(
    "messages",
    { thread: threadId },
  );
  return (
    <div className="mt-3 space-y-2 rounded-md bg-black/[0.03] dark:bg-white/[0.04] p-3">
      {(msgs.data?.results ?? []).map((m) => (
        <div key={m.id} className="text-sm">
          <span className="text-[var(--campus-muted)]">
            {datetime(m.created_at)}
            {m.sender_name ? ` — ${m.sender_name}` : ""} —{" "}
          </span>
          {m.body}
        </div>
      ))}
      <div className="flex gap-2 pt-1">
        <input
          className="flex-1 rounded-md border border-[var(--campus-line)] px-2 py-1 text-sm"
          placeholder="Reply…"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <Button
          size="sm"
          disabled={!body.trim()}
          onClick={async () => {
            await create("messages", { thread: threadId, body });
            setBody("");
            qc.invalidateQueries({ queryKey: ["list", "messages"] });
          }}
        >
          Send
        </Button>
      </div>
    </div>
  );
}
