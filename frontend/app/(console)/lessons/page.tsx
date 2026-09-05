"use client";

import { useState } from "react";
import { useAll, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { PageHeader, Tabs, Badge, Button } from "@/components/ui";
import { act } from "@/lib/resource";
import { useToast } from "@/components/Toast";
import { date, label } from "@/lib/format";

interface Group {
  id: number;
  name: string;
}
interface Term {
  id: number;
  name: string;
}

export default function LessonsPage() {
  const [tab, setTab] = useState("plans");
  const toast = useToast();
  const groups = useAll<Group>("groups");
  const terms = useAll<Term>("terms");
  const units = useAll<{ id: number; title: string }>("curriculum-units");
  const plans = useAll<{ id: number; title: string }>("lesson-plans");
  const groupOpts = options(groups.data, (g) => g.name);
  const termOpts = options(terms.data, (t) => t.name);
  const unitOpts = options(units.data, (u) => u.title);
  const planOpts = options(plans.data, (p) => p.title);

  return (
    <div>
      <PageHeader
        title="Lessons"
        subtitle="Curriculum units, lesson plans (draft → published), and their resources."
      />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "plans", label: "Lesson plans" },
          { key: "units", label: "Curriculum units" },
          { key: "resources", label: "Resources" },
        ]}
      />

      {tab === "units" && (
        <CrudPanel
          resource="curriculum-units"
          singular="unit"
          columns={[
            { header: "Title", cell: (r) => r.title as string },
            {
              header: "Group",
              cell: (r) =>
                groups.data?.find((g) => g.id === r.group)?.name ?? "—",
            },
            { header: "Sequence", cell: (r) => (r.sequence as number) ?? "—" },
          ]}
          fields={[
            { name: "title", label: "Title", required: true },
            { name: "group", label: "Group", type: "select", required: true, options: groupOpts },
            { name: "term", label: "Term", type: "select", options: termOpts },
            { name: "summary", label: "Summary", type: "textarea" },
            { name: "sequence", label: "Sequence", type: "number" },
          ]}
        />
      )}

      {tab === "plans" && (
        <CrudPanel
          resource="lesson-plans"
          singular="lesson plan"
          columns={[
            { header: "Title", cell: (r) => r.title as string },
            { header: "Date", cell: (r) => date(r.date as string) },
            {
              header: "Group",
              cell: (r) =>
                groups.data?.find((g) => g.id === r.group)?.name ?? "—",
            },
            {
              header: "Status",
              cell: (r) => (
                <Badge tone={r.status === "PUBLISHED" ? "green" : "neutral"}>
                  {label(r.status as string)}
                </Badge>
              ),
            },
          ]}
          fields={[
            { name: "title", label: "Title", required: true },
            { name: "group", label: "Group", type: "select", required: true, options: groupOpts },
            { name: "unit", label: "Unit", type: "select", options: unitOpts },
            { name: "date", label: "Date", type: "date", required: true },
            { name: "objectives", label: "Objectives", type: "textarea" },
            { name: "body", label: "Plan", type: "textarea" },
          ]}
          extraRowActions={(row, reload) =>
            row.status !== "PUBLISHED" ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => {
                  try {
                    await act("lesson-plans", row.id as number, "publish");
                    toast("success", "Published");
                    reload();
                  } catch (e) {
                    toast("error", String((e as Error).message));
                  }
                }}
              >
                Publish
              </Button>
            ) : null
          }
        />
      )}

      {tab === "resources" && (
        <CrudPanel
          resource="lesson-resources"
          singular="resource"
          columns={[
            { header: "Title", cell: (r) => r.title as string },
            { header: "Kind", cell: (r) => label(r.kind as string) },
            {
              header: "Link",
              cell: (r) =>
                r.url ? (
                  <a
                    href={r.url as string}
                    className="text-sky-700 hover:underline"
                  >
                    open
                  </a>
                ) : (
                  "—"
                ),
            },
          ]}
          fields={[
            { name: "lesson", label: "Lesson plan", type: "select", required: true, options: planOpts },
            {
              name: "kind",
              label: "Kind",
              type: "select",
              options: ["LINK", "FILE", "NOTE"].map((v) => ({
                value: v,
                label: label(v),
              })),
            },
            { name: "title", label: "Title", required: true },
            { name: "url", label: "URL" },
            { name: "body", label: "Note", type: "textarea" },
          ]}
        />
      )}
    </div>
  );
}
