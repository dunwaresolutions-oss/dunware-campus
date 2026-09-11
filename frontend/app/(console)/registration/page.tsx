"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAll, useQueryParam, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { NestedList } from "@/components/NestedList";
import { ActionButton } from "@/components/ActionButton";
import { Modal } from "@/components/Modal";
import { PageHeader, Tabs, Badge, Button } from "@/components/ui";
import { act, patch, retrieve } from "@/lib/resource";
import { useToast } from "@/components/Toast";
import { apiMessage, date, datetime, label, today } from "@/lib/format";
import { searchStudents } from "@/lib/students";

interface Group {
  id: number;
  name: string;
}
interface AppRow {
  id: string;
  child_first_name: string;
  child_last_name: string;
  child_date_of_birth: string;
  desired_start: string | null;
  desired_group: number | null;
  applicant_name: string;
  applicant_email: string;
  applicant_phone: string;
  notes: string;
  status: string;
  submitted_at: string;
  student: string | null;
}

const OPEN_STATUSES = new Set(["SUBMITTED", "UNDER_REVIEW", "OFFER_MADE", "WAITLISTED"]);

export default function RegistrationPage() {
  const [tab, setTab] = useState("applications");
  const [openApp, setOpenApp] = useState<AppRow | null>(null);
  const paramTab = useQueryParam("tab");
  useEffect(() => {
    if (paramTab) setTab(paramTab);
  }, [paramTab]);
  const groups = useAll<Group>("groups");
  const groupOpts = options(groups.data, (g) => g.name);
  const groupName = (id: number | null | undefined) =>
    id == null ? "—" : (groups.data?.find((g) => g.id === id)?.name ?? String(id));

  return (
    <div>
      <PageHeader
        title="Registration"
        subtitle="An enquiry becomes an application, an application becomes an offer (or a waitlist place), an accepted offer is converted into a real student with an enrolment. Consent decisions are versioned. Press Open on an application to see the whole file and every action in one place."
      />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "applications", label: "Applications" },
          { key: "waitlist", label: "Waitlist" },
          { key: "offers", label: "Offers" },
          { key: "enrolments", label: "Enrolments" },
          { key: "consents", label: "Consents" },
        ]}
      />

      {tab === "applications" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            An <b>application</b> holds the child and applicant details before a
            student record exists. Work it down the lifecycle:{" "}
            <b>Review</b> → <b>Make offer</b> (creates an Offer for a group) →{" "}
            the family accepts on the <b>Offers</b> tab → <b>Convert</b> (creates
            the Student + Enrolment). <b>Waitlist</b> parks it against a group
            instead; <b>Decline</b> ends it. Click a row to edit the fields;
            press <b>Open</b> for the full file — notes, uploaded documents, its
            offers, and every action.
          </p>
          <CrudPanel<AppRow>
            resource="applications"
            singular="application"
            onRowOpen={setOpenApp}
            columns={[
              {
                header: "Child",
                cell: (r) =>
                  `${r.child_first_name ?? ""} ${r.child_last_name ?? ""}`.trim() ||
                  "—",
              },
              { header: "Applicant", cell: (r) => r.applicant_name || "—" },
              { header: "Submitted", cell: (r) => date(r.submitted_at) },
              {
                header: "Status",
                cell: (r) => <Badge>{label(r.status)}</Badge>,
              },
            ]}
            fields={[
              { name: "child_first_name", label: "Child first name", required: true },
              { name: "child_last_name", label: "Child last name", required: true },
              { name: "child_date_of_birth", label: "Child DOB", type: "date", required: true },
              { name: "desired_start", label: "Desired start", type: "date" },
              { name: "desired_group", label: "Desired group", type: "select", options: groupOpts },
              { name: "applicant_name", label: "Applicant name", required: true },
              { name: "applicant_email", label: "Applicant email", required: true },
              { name: "applicant_phone", label: "Applicant phone (encrypted)" },
              { name: "notes", label: "Notes (encrypted)", type: "textarea" },
            ]}
            extraRowActions={(row, reload) => {
              const id = row.id;
              const s = row.status;
              return (
                <>
                  {s === "SUBMITTED" && (
                    <ActionButton
                      label="Review"
                      onRun={() => act("applications", id, "review")}
                      onDone={reload}
                    />
                  )}
                  {s !== "ENROLLED" && s !== "DECLINED" && (
                    <ActionButton
                      label="Make offer"
                      title="Make an offer"
                      fields={[
                        {
                          name: "group",
                          label: "Group",
                          type: "select",
                          required: true,
                          options: groupOpts,
                        },
                        { name: "start_date", label: "Start date", type: "date", required: true },
                        { name: "expires_at", label: "Offer expires", type: "date", required: true },
                      ]}
                      onRun={(v) => act("applications", id, "make_offer", v)}
                      onDone={reload}
                    />
                  )}
                  {s !== "ENROLLED" && (
                    <ActionButton
                      label="Convert"
                      title="Convert to an enrolled student"
                      fields={[
                        {
                          name: "group",
                          label: "Enrol into group",
                          type: "select",
                          options: groupOpts,
                          help: "Optional — leave blank to create the student without an enrolment.",
                        },
                        {
                          name: "start_date",
                          label: "Enrolment start",
                          type: "date",
                          help: "Defaults to today if a group is chosen.",
                        },
                      ]}
                      onRun={(v) =>
                        act("applications", id, "convert", {
                          group: v.group || undefined,
                          start_date: v.start_date || (v.group ? today() : undefined),
                        })
                      }
                      onDone={reload}
                    />
                  )}
                </>
              );
            }}
          />
        </>
      )}

      {tab === "waitlist" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            A <b>waitlist entry</b> parks one application against one group with a{" "}
            <b>priority</b> (lower sorts first). It is a manual list —{" "}
            <b>nothing promotes from it automatically</b>. When a place opens,
            read it top-down and run <b>Make offer</b> on the application you
            choose, then untick <b>Active</b> here once the child is placed.
          </p>
          <CrudPanel
            resource="waitlist"
            singular="waitlist entry"
            columns={[
              { header: "Child", cell: (r) => (r.child_name as string) || `#${r.application}` },
              { header: "Group", cell: (r) => (r.group_name as string) ?? groupName(r.group as number) },
              { header: "Priority", cell: (r) => (r.priority as number) ?? "—" },
              {
                header: "Active",
                cell: (r) => (r.active ? <Badge tone="green">Yes</Badge> : "No"),
              },
            ]}
            fields={[
              { name: "application", label: "Application id", type: "number", required: true },
              {
                name: "group",
                label: "Group",
                type: "select",
                required: true,
                options: groupOpts,
              },
              { name: "priority", label: "Priority", type: "number" },
              { name: "active", label: "Active", type: "checkbox" },
            ]}
            detailTitle={(r) =>
              `Waitlist — ${(r.child_name as string) || `application #${r.application}`}`
            }
            detailFields={[
              {
                label: "Child",
                value: (r) =>
                  (r.child_name as string) || `application #${r.application}`,
              },
              {
                label: "Group",
                value: (r) =>
                  (r.group_name as string) ?? groupName(r.group as number),
              },
              {
                label: "Priority",
                value: (r) => `${(r.priority as number) ?? 100} (lower sorts first)`,
              },
              { label: "Active", value: (r) => (r.active ? "Yes" : "No") },
            ]}
          />
        </>
      )}

      {tab === "offers" && (
        <CrudPanel
          resource="offers"
          singular="offer"
          canCreate={false}
          columns={[
            { header: "Child", cell: (r) => (r.child_name as string) || `#${r.application}` },
            { header: "Group", cell: (r) => (r.group_name as string) ?? groupName(r.group as number) },
            { header: "Start", cell: (r) => date(r.start_date as string) },
            { header: "Expires", cell: (r) => date(r.expires_at as string) },
            {
              header: "Status",
              cell: (r) => <Badge>{label(r.status as string)}</Badge>,
            },
          ]}
          detailTitle={(r) =>
            `Offer — ${(r.child_name as string) || `application #${r.application}`}`
          }
          detailFields={[
            {
              label: "Child",
              value: (r) =>
                (r.child_name as string) || `application #${r.application}`,
            },
            {
              label: "Group",
              value: (r) =>
                (r.group_name as string) ?? groupName(r.group as number),
            },
            { label: "Status", value: (r) => label(r.status as string) },
            { label: "Start date", value: (r) => date(r.start_date as string) },
            { label: "Expires", value: (r) => datetime(r.expires_at as string) },
            {
              label: "Still open",
              value: (r) => (r.is_open ? "Yes" : "No"),
            },
            {
              label: "Answered",
              value: (r) =>
                r.responded_at ? datetime(r.responded_at as string) : "—",
            },
          ]}
          extraRowActions={(row, reload) => (
            <>
              <ActionButton
                label="Accept"
                onRun={() => act("offers", row.id as string, "accept")}
                onDone={reload}
              />
              <ActionButton
                label="Decline"
                variant="ghost"
                confirm="Decline this offer?"
                onRun={() => act("offers", row.id as string, "decline")}
                onDone={reload}
              />
            </>
          )}
        />
      )}

      {tab === "enrolments" && (
        <CrudPanel
          resource="enrolments"
          singular="enrolment"
          columns={[
            {
              header: "Student",
              cell: (r) => (r.student_name as string) || (r.student as string),
            },
            { header: "Group", cell: (r) => (r.group_name as string) ?? groupName(r.group as number) },
            { header: "Start", cell: (r) => date(r.start_date as string) },
            { header: "End", cell: (r) => date(r.end_date as string) },
            {
              header: "Status",
              cell: (r) => (
                <Badge tone={r.status === "ACTIVE" ? "green" : "neutral"}>
                  {label(r.status as string)}
                </Badge>
              ),
            },
          ]}
          fields={[
            {
              name: "student",
              label: "Student",
              type: "search-select",
              required: true,
              search: searchStudents,
              initialLabelKey: "student_name",
            },
            {
              name: "group",
              label: "Group",
              type: "select",
              required: true,
              options: groupOpts,
            },
            { name: "start_date", label: "Start date", type: "date", required: true },
          ]}
          detailTitle={(r) => `Enrolment — ${(r.student_name as string) || "student"}`}
          detailFields={[
            {
              label: "Student",
              value: (r) => (r.student_name as string) || String(r.student),
            },
            {
              label: "Group",
              value: (r) =>
                (r.group_name as string) ?? groupName(r.group as number),
            },
            { label: "Status", value: (r) => label(r.status as string) },
            { label: "Start date", value: (r) => date(r.start_date as string) },
            { label: "End date", value: (r) => date(r.end_date as string) },
            {
              label: "From application",
              value: (r) => (r.source_application ? "Yes" : "Added directly"),
            },
          ]}
          extraRowActions={(row, reload) =>
            row.status === "ACTIVE" ? (
              <ActionButton
                label="End"
                title="End this enrolment"
                fields={[
                  {
                    name: "end_date",
                    label: "End date",
                    type: "date",
                    required: true,
                  },
                ]}
                onRun={(v) => act("enrolments", row.id as string, "end", v)}
                onDone={reload}
              />
            ) : null
          }
        />
      )}

      {tab === "consents" && (
        <CrudPanel
          resource="consents"
          singular="consent"
          columns={[
            {
              header: "Student",
              cell: (r) => (r.student_name as string) || (r.student as string),
            },
            { header: "Kind", cell: (r) => label(r.kind as string) },
            { header: "Version", cell: (r) => (r.version as number) ?? 1 },
            {
              header: "Granted",
              cell: (r) =>
                r.granted ? (
                  <Badge tone="green">Granted</Badge>
                ) : (
                  <Badge tone="red">Withheld</Badge>
                ),
            },
          ]}
          fields={[
            {
              name: "student",
              label: "Student",
              type: "search-select",
              required: true,
              search: searchStudents,
              initialLabelKey: "student_name",
            },
            {
              name: "kind",
              label: "Kind",
              type: "select",
              required: true,
              options: [
                "PHOTO",
                "MEDIA",
                "FIELD_TRIP",
                "DATA_SHARING",
                "MEDICAL_TREATMENT",
                "TECHNOLOGY",
                "SUNSCREEN",
              ].map((v) => ({ value: v, label: label(v) })),
            },
            { name: "granted", label: "Granted", type: "checkbox" },
          ]}
          detailTitle={(r) => `Consent — ${label(r.kind as string)}`}
          detailFields={[
            {
              label: "Student",
              value: (r) => (r.student_name as string) || String(r.student),
            },
            { label: "Kind", value: (r) => label(r.kind as string) },
            { label: "Decision", value: (r) => (r.granted ? "Granted" : "Withheld") },
            { label: "Form version", value: (r) => (r.version as string) ?? "1" },
            {
              label: "Recorded on behalf of",
              value: (r) => (r.granted_by_name as string) || "—",
            },
            {
              label: "Recorded",
              value: (r) =>
                r.recorded_at ? datetime(r.recorded_at as string) : "—",
            },
            { label: "Notes", value: (r) => (r.notes as string) || "—", long: true },
          ]}
        />
      )}

      <ApplicationDrawer
        app={openApp}
        onClose={() => setOpenApp(null)}
        groupName={groupName(openApp?.desired_group)}
        groupOpts={groupOpts}
      />
    </div>
  );
}

/* -------------------------------------------------------- application file */

function ApplicationDrawer({
  app,
  onClose,
  groupName,
  groupOpts,
}: {
  app: AppRow | null;
  onClose: () => void;
  groupName: string;
  groupOpts: { value: string | number; label: string }[];
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [live, setLive] = useState<AppRow | null>(app);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const offers = useAll<{
    id: string;
    application: string;
    group: number;
    group_name?: string;
    start_date: string;
    expires_at: string;
    status: string;
  }>("offers");

  useEffect(() => {
    setLive(app);
    setNotes(app?.notes ?? "");
  }, [app]);

  if (!app || !live) return null;

  const reloadList = () =>
    qc.invalidateQueries({ queryKey: ["list", "applications"] });

  async function refresh() {
    if (!app) return;
    const fresh = await retrieve<AppRow>("applications", app.id);
    setLive(fresh);
    setNotes(fresh.notes ?? "");
    reloadList();
    qc.invalidateQueries({ queryKey: ["all", "offers"] });
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

  const s = live.status;
  const mineOffers = (offers.data ?? []).filter((o) => o.application === app.id);

  return (
    <Modal
      open={!!app}
      onClose={onClose}
      title={`Application — ${live.child_first_name} ${live.child_last_name}`}
      wide
    >
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Badge>{label(live.status)}</Badge>
          <span className="text-[var(--campus-muted)]">
            submitted {date(live.submitted_at)}
          </span>
          {live.desired_start && (
            <span className="text-[var(--campus-muted)]">
              wants to start {date(live.desired_start)}
            </span>
          )}
          <span className="text-[var(--campus-muted)]">
            desired group: {groupName}
          </span>
          {live.student && (
            <Badge tone="green">converted to a student</Badge>
          )}
        </div>

        <div className="grid gap-x-8 gap-y-1 text-sm sm:grid-cols-2">
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
              Child
            </h3>
            <div>
              {live.child_first_name} {live.child_last_name}
            </div>
            <div className="text-[var(--campus-muted)]">
              born {date(live.child_date_of_birth)}
            </div>
          </div>
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
              Applicant
            </h3>
            <div>{live.applicant_name}</div>
            <div className="text-[var(--campus-muted)]">{live.applicant_email}</div>
            <div className="text-[var(--campus-muted)]">
              {live.applicant_phone || "no phone"}
            </div>
          </div>
        </div>

        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
            Notes <span className="normal-case font-normal">(encrypted at rest)</span>
          </h3>
          <textarea
            className="w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm text-[var(--campus-fg)]"
            rows={4}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
          <div className="mt-1 flex justify-end">
            <Button
              size="sm"
              variant="subtle"
              disabled={busy === "notes" || notes === (live.notes ?? "")}
              onClick={() =>
                withBusy("notes", async () => {
                  await patch("applications", app.id, { notes });
                  toast("success", "Notes saved");
                  await refresh();
                })
              }
            >
              {busy === "notes" ? "Saving…" : "Save notes"}
            </Button>
          </div>
        </section>

        <NestedList
          resource="application-documents"
          parentKey="application"
          parentId={app.id}
          title="Documents"
          render={(r) => (
            <span>
              <span className="font-medium">{String(r.title ?? "document")}</span>
              {r.created_at ? (
                <span className="text-[var(--campus-muted)]">
                  {" "}
                  · uploaded {date(String(r.created_at))}
                </span>
              ) : null}
            </span>
          )}
          addFields={[
            { name: "title", label: "Title", required: true },
            { name: "file", label: "File", type: "file", required: true },
          ]}
        />

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
            Offers on this application ({mineOffers.length})
          </h3>
          {mineOffers.length === 0 ? (
            <p className="text-sm text-[var(--campus-muted)]">
              None yet. Use <b>Make offer</b> below.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--campus-line)] rounded-md border border-[var(--campus-line)] text-sm">
              {mineOffers.map((o) => (
                <li
                  key={o.id}
                  className="flex items-center justify-between gap-2 px-3 py-2"
                >
                  <span>
                    {o.group_name ?? `group #${o.group}`} · start{" "}
                    {date(o.start_date)} · expires {date(o.expires_at)}
                  </span>
                  <Badge
                    tone={
                      o.status === "ACCEPTED"
                        ? "green"
                        : o.status === "DECLINED" || o.status === "EXPIRED"
                          ? "neutral"
                          : "amber"
                    }
                  >
                    {label(o.status)}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-[var(--campus-line)] pt-3">
          {s === "SUBMITTED" && (
            <Button
              variant="ghost"
              disabled={busy === "review"}
              onClick={() =>
                withBusy("review", async () => {
                  await act("applications", app.id, "review");
                  toast("success", "Marked under review");
                  await refresh();
                })
              }
            >
              Review
            </Button>
          )}
          {s !== "ENROLLED" && s !== "DECLINED" && (
            <ActionButton
              label="Make offer"
              title="Make an offer"
              fields={[
                { name: "group", label: "Group", type: "select", required: true, options: groupOpts },
                { name: "start_date", label: "Start date", type: "date", required: true },
                { name: "expires_at", label: "Offer expires", type: "date", required: true },
              ]}
              onRun={(v) => act("applications", app.id, "make_offer", v)}
              onDone={refresh}
            />
          )}
          {s !== "ENROLLED" && s !== "DECLINED" && (
            <ActionButton
              label="Waitlist"
              variant="ghost"
              title="Park this application on a group's waitlist"
              fields={[
                { name: "group", label: "Group", type: "select", required: true, options: groupOpts },
                { name: "priority", label: "Priority (lower = first)", type: "number" },
              ]}
              onRun={(v) => act("applications", app.id, "waitlist", v)}
              onDone={refresh}
            />
          )}
          {s !== "ENROLLED" && (
            <ActionButton
              label="Convert"
              title="Convert to an enrolled student"
              fields={[
                {
                  name: "group",
                  label: "Enrol into group",
                  type: "select",
                  options: groupOpts,
                  help: "Optional — leave blank to create the student without an enrolment.",
                },
                { name: "start_date", label: "Enrolment start", type: "date", help: "Defaults to today if a group is chosen." },
              ]}
              onRun={(v) =>
                act("applications", app.id, "convert", {
                  group: v.group || undefined,
                  start_date: v.start_date || (v.group ? today() : undefined),
                })
              }
              onDone={refresh}
            />
          )}
          {OPEN_STATUSES.has(s) && (
            <ActionButton
              label="Decline"
              variant="ghost"
              confirm="Decline this application?"
              onRun={() => act("applications", app.id, "decline")}
              onDone={refresh}
            />
          )}
        </div>
      </div>
    </Modal>
  );
}
