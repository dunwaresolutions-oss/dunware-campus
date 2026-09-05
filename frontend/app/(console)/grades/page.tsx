"use client";

import { useState } from "react";
import { useAll, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { PageHeader, Tabs, Badge, Button } from "@/components/ui";
import { act } from "@/lib/resource";
import { useToast } from "@/components/Toast";
import { date, label } from "@/lib/format";

export default function GradesPage() {
  const [tab, setTab] = useState("assessments");
  const toast = useToast();
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
        <CrudPanel
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
          extraRowActions={(row, reload) => (
            <>
              {row.status === "DRAFT" && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    run("report-cards", row.id as number, "generate", reload)
                  }
                >
                  Generate
                </Button>
              )}
              {row.status === "FINALIZED" && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    run("report-cards", row.id as number, "release", reload)
                  }
                >
                  Release
                </Button>
              )}
            </>
          )}
        />
      )}
    </div>
  );
}
