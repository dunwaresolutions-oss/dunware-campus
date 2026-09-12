"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAll, useList, useQueryParam, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { NestedList } from "@/components/NestedList";
import { Modal } from "@/components/Modal";
import { RecordForm } from "@/components/RecordForm";
import { PageHeader, Tabs, Badge, Button, Card, Spinner } from "@/components/ui";
import { act, create, patch, retrieve } from "@/lib/resource";
import { api } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { apiMessage, date, label } from "@/lib/format";
import { searchStudents } from "@/lib/students";
import { SearchSelect } from "@/components/SearchSelect";

interface ReportCardRow {
  id: string;
  student: string;
  student_name?: string;
  term: number;
  term_name?: string;
  status: "DRAFT" | "FINALIZED" | "RELEASED";
  summary_narrative: string;
  document_url: string | null;
  grading_scheme: string | null;
  grading_scheme_name: string | null;
  cumulative_gpa: number | null;
  generated_at: string | null;
  released_at: string | null;
}

export default function GradesPage() {
  const [tab, setTab] = useState("assessments");
  const [openCard, setOpenCard] = useState<ReportCardRow | null>(null);
  const [resultsStudent, setResultsStudent] = useState("");
  const [resultsSubject, setResultsSubject] = useState("");
  const [cardsStudent, setCardsStudent] = useState("");
  const [cardsSubject, setCardsSubject] = useState("");
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
  const groupOpts = options(groups.data, (g) => g.name);
  const termOpts = options(terms.data, (t) => t.name);
  const schemeOpts = options(schemes.data, (s) => s.name);
  const assessmentOpts = options(assessments.data, (a) => a.title);

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
          { key: "grading", label: "Report card grading" },
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
          detailTitle={(r) => `Scheme — ${r.name as string}`}
          detailFields={[
            { label: "Name", value: (r) => r.name as string },
            { label: "Kind", value: (r) => label(r.kind as string) },
            {
              label: "Group",
              value: (r) =>
                groups.data?.find((g) => g.id === r.group)?.name ?? "—",
            },
            {
              label: "Term",
              value: (r) => terms.data?.find((t) => t.id === r.term)?.name ?? "—",
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
          detailTitle={(r) => `Assessment — ${r.title as string}`}
          detailFields={[
            { label: "Title", value: (r) => r.title as string },
            {
              label: "Scheme",
              value: (r) =>
                schemes.data?.find((s) => s.id === r.scheme)?.name ?? "—",
            },
            {
              label: "Group",
              value: (r) =>
                groups.data?.find((g) => g.id === r.group)?.name ?? "—",
            },
            { label: "Date", value: (r) => date(r.date as string) },
            { label: "Max mark", value: (r) => (r.max_mark as number) ?? "—" },
            {
              label: "Released to parents",
              value: (r) =>
                r.released
                  ? `Yes${r.released_at ? ` (${date(r.released_at as string)})` : ""}`
                  : "No — still a draft",
            },
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
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="w-56">
              <SearchSelect
                value={resultsStudent}
                onChange={setResultsStudent}
                search={searchStudents}
                placeholder="Filter by student…"
              />
            </span>
            <input
              value={resultsSubject}
              onChange={(e) => setResultsSubject(e.target.value)}
              placeholder="Filter by subject (e.g. English)…"
              className="w-56 rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-1.5 text-sm text-[var(--campus-fg)] focus:border-[var(--campus-accent)] focus:outline-none"
            />
            {(resultsStudent || resultsSubject) && (
              <button
                className="text-xs text-[var(--campus-accent)] hover:underline"
                onClick={() => {
                  setResultsStudent("");
                  setResultsSubject("");
                }}
              >
                Clear
              </button>
            )}
          </div>
          <CrudPanel
            resource="assessment-results"
            singular="result"
            query={{ student: resultsStudent || undefined, subject: resultsSubject || undefined }}
            columns={[
            {
              header: "Assessment",
              cell: (r) =>
                assessments.data?.find((a) => a.id === r.assessment)?.title ??
                r.assessment,
            },
            {
              header: "Student",
              cell: (r) => (r.student_name as string) || String(r.student),
            },
            { header: "Mark", cell: (r) => (r.mark as string) ?? "—" },
            { header: "Level", cell: (r) => (r.level as number) ?? "—" },
          ]}
          fields={[
            { name: "assessment", label: "Assessment", type: "select", required: true, options: assessmentOpts },
            {
              name: "student", label: "Student", type: "search-select", required: true,
              search: searchStudents, initialLabelKey: "student_name",
            },
            { name: "mark", label: "Mark", type: "number" },
            { name: "level", label: "Level", type: "number" },
            { name: "narrative", label: "Narrative (encrypted)", type: "textarea" },
          ]}
          detailTitle={() => "Result"}
          detailFields={[
            {
              label: "Assessment",
              value: (r) =>
                assessments.data?.find((a) => a.id === r.assessment)?.title ??
                String(r.assessment),
            },
            {
              label: "Student",
              value: (r) => (r.student_name as string) || String(r.student),
            },
            { label: "Mark", value: (r) => (r.mark as string) ?? "—" },
            { label: "Level", value: (r) => (r.level as number) ?? "—" },
            {
              label: "Narrative",
              long: true,
              value: (r) => (r.narrative as string) || "—",
            },
          ]}
          />
        </>
      )}

      {tab === "reportcards" && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="w-56">
              <SearchSelect
                value={cardsStudent}
                onChange={setCardsStudent}
                search={searchStudents}
                placeholder="Filter by student…"
              />
            </span>
            <input
              value={cardsSubject}
              onChange={(e) => setCardsSubject(e.target.value)}
              placeholder="Filter by subject (e.g. English)…"
              className="w-56 rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-1.5 text-sm text-[var(--campus-fg)] focus:border-[var(--campus-accent)] focus:outline-none"
            />
            {(cardsStudent || cardsSubject) && (
              <button
                className="text-xs text-[var(--campus-accent)] hover:underline"
                onClick={() => {
                  setCardsStudent("");
                  setCardsSubject("");
                }}
              >
                Clear
              </button>
            )}
          </div>
          <CrudPanel<ReportCardRow>
            resource="report-cards"
            singular="report card"
            query={{ student: cardsStudent || undefined, subject: cardsSubject || undefined }}
            onRowOpen={setOpenCard}
            columns={[
            {
              header: "Student",
              cell: (r) => (r.student_name as string) || r.student,
            },
            {
              header: "Term",
              cell: (r) =>
                (r.term_name as string) ||
                terms.data?.find((t) => t.id === r.term)?.name ||
                r.term,
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
            {
              name: "student", label: "Student", type: "search-select", required: true,
              search: searchStudents, initialLabelKey: "student_name",
            },
            { name: "term", label: "Term", type: "select", required: true, options: termOpts },
            { name: "summary_narrative", label: "Summary (encrypted)", type: "textarea" },
          ]}
          />
        </>
      )}

      {tab === "grading" && <GradingSchemes />}

      <ReportCardDrawer
        card={openCard}
        onClose={() => setOpenCard(null)}
        studentName={openCard?.student_name || openCard?.student || ""}
        termName={
          terms.data?.find((t) => t.id === openCard?.term)?.name ??
          String(openCard?.term ?? "")
        }
        groupOpts={groupOpts}
      />
    </div>
  );
}

function ReportCardDrawer({
  card,
  onClose,
  studentName,
  termName,
  groupOpts,
}: {
  card: ReportCardRow | null;
  onClose: () => void;
  studentName: string;
  termName: string;
  groupOpts: { value: string | number; label: string }[];
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
          {live.grading_scheme_name && (
            <span className="text-[var(--campus-muted)]">
              grading: {live.grading_scheme_name}
            </span>
          )}
          {live.cumulative_gpa != null && (
            <Badge tone="violet">Cumulative GPA {Number(live.cumulative_gpa).toFixed(2)}</Badge>
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
            const gradeLabel = r.grade_label ? String(r.grade_label) : null;
            const gpaPoints = r.gpa_points != null ? String(r.gpa_points) : null;
            return (
              <span>
                <span className="font-medium">{String(r.subject ?? "")}</span>
                {r.group_name ? (
                  <span className="text-[var(--campus-muted)]"> ({String(r.group_name)})</span>
                ) : null}
                {mark ? ` · mark ${mark}` : ""}
                {gradeLabel ? ` · grade ${gradeLabel}` : ""}
                {gpaPoints ? ` (${gpaPoints} pts)` : ""}
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
                  { name: "group", label: "Your class (optional)", type: "select", options: groupOpts },
                  { name: "mark", label: "Mark", type: "number" },
                  { name: "level", label: "Level", type: "number" },
                  { name: "comment", label: "Comment (encrypted)", type: "textarea" },
                  { name: "order", label: "Order", type: "number" },
                ]
              : undefined
          }
        />
        <p className="text-xs text-[var(--campus-muted)]">
          Every teacher of this student can add their own subject here — pick your
          class so it&apos;s clear whose entry is whose.
        </p>

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

/* --------------------------------------------------------- grading scheme */

interface GradeBandRow {
  id: string;
  scheme: string;
  label: string;
  min_percent: number;
  max_percent: number;
  gpa_points: number | null;
  description: string;
  order: number;
}
interface SchemeRow {
  id: string;
  name: string;
  description: string;
  uses_gpa: boolean;
  gpa_scale: number | null;
  is_active: boolean;
  bands: GradeBandRow[];
}

function GradingSchemes() {
  const qc = useQueryClient();
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState<SchemeRow | null>(null);
  const q = useList<SchemeRow>("grading-schemes");
  const reload = () => qc.invalidateQueries({ queryKey: ["list", "grading-schemes"] });
  const schemes = q.data?.results ?? [];

  async function activate(id: string) {
    try {
      await act("grading-schemes", id, "activate");
      toast("success", "Grading scheme activated");
      reload();
      if (open) setOpen((o) => (o ? { ...o, is_active: o.id === id } : o));
    } catch (e) {
      toast("error", apiMessage(e));
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-[var(--campus-muted)]">
        Exactly one scheme is <b>active</b> at a time — it&apos;s what every report card&apos;s
        grade column, and cumulative GPA if the scheme uses one, is computed from
        going forward. A card already generated keeps whatever scheme was active
        when it was made, so changing this never rewrites history. With none
        active, report cards just show the raw mark.
      </p>
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setCreating(true)}>
          New scheme
        </Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {schemes.map((s) => (
          <Card key={s.id} className="p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{s.name}</span>
                  {s.is_active && <Badge tone="green">Active</Badge>}
                  {s.uses_gpa && <Badge tone="violet">GPA / {Number(s.gpa_scale ?? 4).toFixed(2)}</Badge>}
                </div>
                {s.description && (
                  <p className="mt-1 text-xs text-[var(--campus-muted)]">{s.description}</p>
                )}
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-1">
              {s.bands.map((b) => (
                <span
                  key={b.id}
                  className="rounded-full border border-[var(--campus-line)] px-2 py-0.5 text-xs"
                  title={b.description}
                >
                  {b.label} ({b.min_percent}–{b.max_percent}%
                  {b.gpa_points != null ? ` · ${b.gpa_points}` : ""})
                </span>
              ))}
              {s.bands.length === 0 && (
                <span className="text-xs text-[var(--campus-muted)]">No bands yet.</span>
              )}
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setOpen(s)}>
                Manage bands
              </Button>
              {!s.is_active && (
                <Button size="sm" variant="subtle" onClick={() => activate(s.id)}>
                  Activate
                </Button>
              )}
            </div>
          </Card>
        ))}
        {schemes.length === 0 && !q.isLoading && (
          <p className="text-sm text-[var(--campus-muted)]">No grading schemes yet.</p>
        )}
      </div>

      <Modal open={creating} onClose={() => setCreating(false)} title="New grading scheme">
        <RecordForm
          fields={[
            { name: "name", label: "Name", required: true },
            { name: "description", label: "Description" },
            { name: "uses_gpa", label: "Uses a GPA", type: "checkbox" },
            { name: "gpa_scale", label: "GPA scale (e.g. 4.00)", type: "number" },
          ]}
          submitLabel="Create scheme"
          onSubmit={async (v) => {
            await create("grading-schemes", v);
            toast("success", "Scheme created — add its bands next");
            setCreating(false);
            reload();
          }}
          onCancel={() => setCreating(false)}
        />
      </Modal>

      <Modal
        open={!!open}
        onClose={() => setOpen(null)}
        title={open ? `Bands — ${open.name}` : "Bands"}
        wide
      >
        {open && (
          <div className="space-y-3">
            {!open.is_active && (
              <Button size="sm" onClick={() => activate(open.id)}>
                Activate this scheme
              </Button>
            )}
            <NestedList
              resource="grade-bands"
              parentKey="scheme"
              parentId={open.id}
              title="Bands, highest first"
              render={(r) => (
                <span>
                  <span className="font-medium">{String(r.label)}</span>{" "}
                  {String(r.min_percent)}–{String(r.max_percent)}%
                  {r.gpa_points != null ? ` · ${r.gpa_points} pts` : ""}
                  {r.description ? (
                    <span className="text-[var(--campus-muted)]"> — {String(r.description)}</span>
                  ) : null}
                </span>
              )}
              addFields={[
                { name: "label", label: "Label", required: true, placeholder: "A, Level 4, 7, Distinction…" },
                { name: "min_percent", label: "Min %", type: "number", required: true },
                { name: "max_percent", label: "Max %", type: "number", required: true },
                { name: "gpa_points", label: "GPA points (if this scheme uses a GPA)", type: "number" },
                { name: "description", label: "Description" },
                { name: "order", label: "Order (highest band = 1)", type: "number" },
              ]}
            />
          </div>
        )}
      </Modal>
    </div>
  );
}
