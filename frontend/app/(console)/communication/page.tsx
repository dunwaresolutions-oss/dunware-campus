"use client";

import { useState } from "react";
import { useAll, useList, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { create, act } from "@/lib/resource";
import { PageHeader, Tabs, Badge, Button, Card, Spinner } from "@/components/ui";
import { Modal } from "@/components/Modal";
import { RecordForm } from "@/components/RecordForm";
import { useToast } from "@/components/Toast";
import { datetime, apiMessage, label } from "@/lib/format";
import { useQueryClient } from "@tanstack/react-query";

export default function CommunicationPage() {
  const [tab, setTab] = useState("threads");
  const toast = useToast();
  const groups = useAll<{ id: number; name: string }>("groups");
  const students = useAll<{ id: string; display_name: string }>("students");
  const groupOpts = options(groups.data, (g) => g.name);
  const studentOpts = options(students.data, (s) => s.display_name);

  return (
    <div>
      <PageHeader
        title="Messages"
        subtitle="Announcements, staff ↔ parent threads, incident reports with acknowledgement, and the outbound email log. Email only."
      />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "threads", label: "Threads" },
          { key: "announcements", label: "Announcements" },
          { key: "incidents", label: "Incident reports" },
          { key: "email", label: "Email log" },
        ]}
      />

      {tab === "announcements" && (
        <CrudPanel
          resource="announcements"
          singular="announcement"
          columns={[
            { header: "Title", cell: (r) => r.title as string },
            { header: "Audience", cell: (r) => label(r.audience as string) },
            {
              header: "Published",
              cell: (r) =>
                r.published_at ? (
                  <Badge tone="green">{datetime(r.published_at as string)}</Badge>
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
              options: [
                "ALL_STAFF",
                "ALL_PARENTS",
                "GROUP",
                "WHOLE_SITE",
              ].map((v) => ({ value: v, label: label(v) })),
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
                    await act("announcements", row.id as number, "publish");
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
      )}

      {tab === "threads" && <Threads studentOpts={studentOpts} />}

      {tab === "incidents" && (
        <CrudPanel
          resource="incident-reports"
          singular="incident report"
          columns={[
            {
              header: "Student",
              cell: (r) =>
                students.data?.find((s) => s.id === r.student)?.display_name ??
                r.student,
            },
            { header: "Category", cell: (r) => label(r.category as string) },
            { header: "When", cell: (r) => datetime(r.occurred_at as string) },
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
                  {label(r.status as string)}
                </Badge>
              ),
            },
          ]}
          fields={[
            { name: "student", label: "Student", type: "select", required: true, options: studentOpts },
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
                    await act("incident-reports", row.id as number, "notify");
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
      )}

      {tab === "email" && (
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
        />
      )}
    </div>
  );
}

function Threads({
  studentOpts,
}: {
  studentOpts: { value: string | number; label: string }[];
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const threads = useList<{
    id: string;
    subject: string;
    student: string | null;
    closed: boolean;
    message_count?: number;
    last_message_at: string | null;
  }>("message-threads");

  return (
    <Card>
      <div className="flex justify-end border-b border-neutral-100 p-3">
        <Button size="sm" onClick={() => setCreating(true)}>
          New thread
        </Button>
      </div>
      {threads.isLoading ? (
        <Spinner />
      ) : (
        <ul className="divide-y divide-neutral-100 text-sm">
          {(threads.data?.results ?? []).map((t) => (
            <li key={t.id} className="px-4 py-3">
              <button
                className="flex w-full items-center justify-between text-left"
                onClick={() => setOpen(open === t.id ? null : t.id)}
              >
                <span className="font-medium">{t.subject}</span>
                <span className="text-xs text-neutral-500">
                  {t.message_count ?? 0} msg ·{" "}
                  {datetime(t.last_message_at)}
                  {t.closed && " · closed"}
                </span>
              </button>
              {open === t.id && <ThreadMessages threadId={t.id} />}
            </li>
          ))}
          {(threads.data?.results ?? []).length === 0 && (
            <li className="p-4 text-neutral-500">No threads yet.</li>
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
            { name: "student", label: "About student", type: "select", options: studentOpts },
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
    </Card>
  );
}

function ThreadMessages({ threadId }: { threadId: string }) {
  const qc = useQueryClient();
  const [body, setBody] = useState("");
  const msgs = useList<{ id: string; body: string; created_at: string }>(
    "messages",
    { thread: threadId },
  );
  return (
    <div className="mt-3 space-y-2 rounded-md bg-neutral-50 p-3">
      {(msgs.data?.results ?? []).map((m) => (
        <div key={m.id} className="text-sm">
          <span className="text-neutral-500">{datetime(m.created_at)} — </span>
          {m.body}
        </div>
      ))}
      <div className="flex gap-2 pt-1">
        <input
          className="flex-1 rounded-md border border-neutral-300 px-2 py-1 text-sm"
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
