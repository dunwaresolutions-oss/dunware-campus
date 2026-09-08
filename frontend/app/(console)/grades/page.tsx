"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAll, useQueryParam, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { NestedList } from "@/components/NestedList";
import { Modal } from "@/components/Modal";
import { PageHeader, Tabs, Badge, Button, Spinner } from "@/components/ui";
import { act, patch, retrieve } from "@/lib/resource";
import { api } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { apiMessage, date, label } from "@/lib/format";

interface ReportCardRow {
  id: string;
  student: string;
  term: number;
  status: "DRAFT" | "FINALIZED" | "RELEASED";
  summary_narrative: string;
  document_url: string | null;
  generated_at: string | null;
  released_at: string | null;
}

export default function GradesPage() {
  const [tab, setTab] = useState("assessments");
  const [openCard, setOpenCard] = useState<ReportCardRow | null>(null);
  const toast = useToast();
  const paramTab = useQueryParam("tab");
  const focusId = useQueryParam("focus");

  useEffect(() => {
    if (paramTab) setTab(paramTab);
  }, [paramTab]);
  useEffect(() => {
    if (!focusId) return;
    setTab("reportcards");
    retrieve<ReportCardRow>("report-cards", focusId)
      .then(setOpenCard)
      .catch(() => {});
  }, [focusId]);
  const groups = useAll<{ id: number; name: string }>("groups");
  const terms = useAll<{ id: number; name: string }>("terms");
  const schemes = useAll<{ id: number; name: string }>("assessment-schemes");
  const assessments = useAll<{ id: number; title: string }>("assessments");
  const students = useAll<{ id: string; display_name: string }>("students");
  const groupOpts = options(groups.data, (g) => g.name);
  const termOpts = options(terms.data, (t) => t.name);
  const schemeOpts = options(schemes.data, (s) => s.name);
  const assessmentOpts = options(assessments.data, (a) => a.title);
  const studentOpts = options(students.data, (s) => s.display_name);

  async function run(res: string, id: number, verb: string, reload: () => void) {
    try {
      await act(res, id, verb);
      toast("success", `${label(verb)} done`);
      reload();
    } catch (e) {
      toast("error", String((e as Error).message));
    }
  }

  return (
    <div>
      <PageHeader
        title="Grades"
        subtitle="Assessment schemes (rubric / narrative / marks), assessments, per-student results, and report cards."
      />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "assessments", label: "Assessments" },
          { key: "results", label: "Results" },
          { key: "schemes", label: "Schemes" },
          { key: "reportcards", label: "Report cards" },
        ]}
      />

      {tab === "schemes" && (
        <CrudPanel
          resource="assessment-schemes"
          singular="scheme"
          columns={[
            { header: "Name", cell: (r) => r.name as string },
            { header: "Kind", cell: (r) => label(r.kind as string) },
            {
              header: "Group",
              cell: (r) =>
                groups.data?.find((g) => g.id === r.group)?.name ?? "—",
            },
          ]}
          fields={[
            { name: "name", label: "Name", required: true },
            { name: "group", label: "Group", type: "select", required: true, options: groupOpts },
            { name: "term", label: "Term", type: "select", options: termOpts },
            {
              name: "kind",
              label: "Kind",
              type: "select",
              options: ["MARKS", "RUBRIC", "NARRATIVE", "MIXED"].map((v) => ({
                value: v,
                label: label(v),
              })),
            },
          ]}
        />
      )}

      {tab === "assessments" && (
        <CrudPanel
          resource="assessments"
          singular="assessment"
          columns={[
            { header: "Title", cell: (r) => r.title as string },
            { header: "Date", cell: (r) => date(r.date as string) },
            {
              header: "Group",
              cell: (r) =>
                groups.data?.find((g) => g.id === r.group)?.name ?? "—",
            },
            {
              header: "Released",
              cell: (r) =>
                r.released ? (
                  <Badge tone="green">Released</Badge>
                ) : (
                  <Badge>Draft</Badge>
                ),
            },
          ]}
          fields={[
            { name: "scheme", label: "Scheme", type: "select", required: true, options: schemeOpts },
            { name: "group", label: "Group", type: "select", required: true, options: groupOpts },
            { name: "title", label: "Title", required: true },
            { name: "date", label: "Date", type: "date", required: true },
            { name: "max_mark", label: "Max mark", type: "number" },
          ]}
          extraRowActions={(row, reload) =>
            !row.released ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  run("assessments", row.id as number, "release", reload)
                }
              >
                Release
              </Button>
            ) : null
          }
        />
      )}

      {tab === "results" && (
        <CrudPanel
          resource="assessment-results"
          singular="result"
          columns={[
            {
              header: "Assessment",
              cell: (r) =>
                assessments.data?.find((a) => a.id === r.assessment)?.title ??
                r.assessment,
            },
            {
              header: "Student",
              cell: (r) =>
                students.data?.find((s) => s.id === r.student)?.display_name ??
                r.student,
            },
            { header: "Mark", cell: (r) => (r.mark as string) ?? "—" },
            { header: "Level", cell: (r) => (r.level as number) ?? "—" },
          ]}
          fields={[
            { name: "assessment", label: "Assessment", type: "select", required: true, options: assessmentOpts },
            { name: "student", label: "Student", type: "select", required: true, options: studentOpts },
            { name: "mark", label: "Mark", type: "number" },
            { name: "level", label: "Level", type: "number" },
            { name: "narrative", label: "Narrative (encrypted)", type: "textarea" },
          ]}
        />
      )}

      {tab === "reportcards" && (
        <CrudPanel<ReportCardRow>
          resource="report-cards"
          singular="report card"
          columns={[
            {
              header: "Student",
              cell: (r) =>
                students.data?.find((s) => s.id === r.student)?.display_name ??
                r.student,
            },
            {
              header: "Term",
              cell: (r) =>
                terms.data?.find((t) => t.id === r.term)?.name ?? r.term,
            },
            {
              header: "Status",
              cell: (r) => (
                <Badge
                  tone={
                    r.status === "RELEASED"
                      ? "green"
                      : r.status === "FINALIZED"
                        ? "sky"
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
            { name: "term", label: "Term", type: "select", required: true, options: termOpts },
            { name: "summary_narrative", label: "Summary (encrypted)", type: "textarea" },
          ]}
          extraRowActions={(row) => (
            <Button size="sm" variant="ghost" onClick={() => setOpenCard(row)}>
              Open
            </Button>
          )}
        />
      )}

      <ReportCardDrawer
        card={openCard}
        onClose={() => setOpenCard(null)}
        studentName={
          students.data?.find((s) => s.id === openCard?.student)?.display_name ??
          openCard?.student ??
          ""
        }
        termName={
          terms.data?.find((t) => t.id === openCard?.term)?.name ??
          String(openCard?.term ?? "")
        }
      />
    </div>
  );
}

function ReportCardDrawer({
  card,
  onClose,
  studentName,
  termName,
}: {
  card: ReportCardRow | null;
  onClose: () => void;
  studentName: string;
  termName: string;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [live, setLive] = useState<ReportCardRow | null>(card);
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    setLive(card);
    setSummary(card?.summary_narrative ?? "");
  }, [card]);

  if (!card || !live) return null;

  const reloadList = () =>
    qc.invalidateQueries({ queryKey: ["list", "report-cards"] });

  async function refresh() {
    if (!card) return;
    const fresh = await retrieve<ReportCardRow>("report-cards", card.id);
    setLive(fresh);
    setSummary(fresh.summary_narrative ?? "");
    reloadList();
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

  const released = live.status === "RELEASED";
  const editable = !released;

  return (
    <Modal open={!!card} onClose={onClose} title={`Report card — ${studentName}`} wide>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Badge
            tone={
              live.status === "RELEASED"
                ? "green"
                : live.status === "FINALIZED"
                  ? "sky"
                  : "neutral"
            }
          >
            {label(live.status)}
          </Badge>
          <span className="text-[var(--campus-muted)]">{termName}</span>
          {live.generated_at && (
            <span className="text-[var(--campus-muted)]">
              generated {date(live.generated_at)}
            </span>
          )}
          {live.released_at && (
            <span className="text-[var(--campus-muted)]">
              released {date(live.released_at)}
            </span>
          )}
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-[var(--campus-muted)]">
            Summary narrative
          </label>
          <textarea
            className="w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm text-[var(--campus-fg)]"
            rows={4}
            value={summary}
            disabled={!editable}
            onChange={(e) => setSummary(e.target.value)}
          />
          {editable && (
            <div className="mt-1 flex justify-end">
              <Button
                size="sm"
                variant="subtle"
                disabled={busy === "summary" || summary === live.summary_narrative}
                onClick={() =>
                  withBusy("summary", async () => {
                    await patch("report-cards", card.id, {
                      summary_narrative: summary,
                    });
                    toast("success", "Summary saved");
                    await refresh();
                  })
                }
              >
                Save summary
              </Button>
            </div>
          )}
        </div>

        <NestedList
          resource="report-card-entries"
          parentKey="report_card"
          parentId={card.id}
          title="Subjects / learning areas"
          render={(r) => {
            const mark = r.mark == null || r.mark === "" ? null : String(r.mark);
            const lvl = r.level == null || r.level === "" ? null : String(r.level);
            return (
              <span>
                <span className="font-medium">{String(r.subject ?? "")}</span>
                {mark ? ` · mark ${mark}` : ""}
                {lvl ? ` · level ${lvl}` : ""}
                {r.comment ? (
                  <span className="text-[var(--campus-muted)]">
                    {" "}
                    — {String(r.comment)}
                  </span>
                ) : null}
              </span>
            );
          }}
          addFields={
            editable
              ? [
                  { name: "subject", label: "Subject / learning area", required: true },
                  { name: "mark", label: "Mark", type: "number" },
                  { name: "level", label: "Level", type: "number" },
                  { name: "comment", label: "Comment (encrypted)", type: "textarea" },
                  { name: "order", label: "Order", type: "number" },
                ]
              : undefined
          }
        />

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-[var(--campus-line)] pt-3">
          <Button
            variant="ghost"
            disabled={busy === "preview"}
            onClick={() =>
              withBusy("preview", async () => {
                const res = await api<{ html: string }>(
                  `/report-cards/${card.id}/preview/`,
                );
                setPreview(res.html);
              })
            }
          >
            {busy === "preview" ? "Rendering…" : "Preview"}
          </Button>
          {live.document_url && (
            <a
              href={live.document_url}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-[var(--campus-accent)] hover:underline"
            >
              Open generated file
            </a>
          )}
          {!released && (
            <Button
              disabled={busy === "generate"}
              onClick={() =>
                withBusy("generate", async () => {
                  await act("report-cards", card.id, "generate");
                  toast(
                    "success",
                    live.status === "DRAFT"
                      ? "Generated — now finalized"
                      : "Regenerated",
                  );
                  await refresh();
                })
              }
            >
              {live.status === "DRAFT" ? "Generate" : "Regenerate"}
            </Button>
          )}
          {live.status === "FINALIZED" && (
            <Button
              disabled={busy === "release"}
              onClick={() =>
                withBusy("release", async () => {
                  await act("report-cards", card.id, "release");
                  toast("success", "Released to guardians");
                  await refresh();
                })
              }
            >
              Release to guardians
            </Button>
          )}
        </div>

        {!editable && (
          <p className="text-xs text-[var(--campus-muted)]">
            A released report card is locked. Guardians can now read it on the portal.
          </p>
        )}
        {live.status === "FINALIZED" && (
          <p className="text-xs text-[var(--campus-muted)]">
            Edited the subjects or summary? Press <b>Regenerate</b> before releasing so
            the guardians&apos; copy matches.
          </p>
        )}
      </div>

      <Modal
        open={preview != null}
        onClose={() => setPreview(null)}
        title="Report card preview"
        wide
      >
        {preview == null ? (
          <Spinner />
        ) : (
          <iframe
            title="Report card preview"
            srcDoc={preview}
            className="h-[70vh] w-full rounded-lg border border-[var(--campus-line)] bg-white"
          />
        )}
      </Modal>
    </Modal>
  );
}
