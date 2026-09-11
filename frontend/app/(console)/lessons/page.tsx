"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAll, useQueryParam, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { NestedList } from "@/components/NestedList";
import { Modal } from "@/components/Modal";
import { PageHeader, Tabs, Badge, Button } from "@/components/ui";
import { act, patch, retrieve } from "@/lib/resource";
import { useToast } from "@/components/Toast";
import { apiMessage, date, label } from "@/lib/format";

interface Group {
  id: number;
  name: string;
}
interface Term {
  id: number;
  name: string;
}
interface UnitRow {
  id: number;
  group: number;
  term: number | null;
  title: string;
  summary: string;
  sequence: number;
}
interface PlanRow {
  id: number;
  group: number;
  unit: number | null;
  date: string;
  title: string;
  objectives: string;
  body: string;
  status: "DRAFT" | "PUBLISHED";
  resources?: { id: number }[];
}

const STATUS_OPTS = [
  { value: "DRAFT", label: "Draft" },
  { value: "PUBLISHED", label: "Published" },
];

export default function LessonsPage() {
  const [tab, setTab] = useState("plans");
  const [openPlan, setOpenPlan] = useState<PlanRow | null>(null);
  const [openUnit, setOpenUnit] = useState<UnitRow | null>(null);
  const [planFilter, setPlanFilter] = useState({ group: "", unit: "", term: "", status: "" });
  const [unitFilter, setUnitFilter] = useState({ group: "", term: "" });
  const [resourceFilter, setResourceFilter] = useState({ group: "" });

  const paramTab = useQueryParam("tab");
  useEffect(() => {
    if (paramTab) setTab(paramTab);
  }, [paramTab]);

  const groups = useAll<Group>("groups");
  const terms = useAll<Term>("terms");
  const units = useAll<UnitRow>("curriculum-units");
  const plans = useAll<PlanRow>("lesson-plans");
  const groupOpts = options(groups.data, (g) => g.name);
  const termOpts = options(terms.data, (t) => t.name);
  const unitOpts = options(units.data, (u) => u.title);
  const planOpts = options(plans.data, (p) => p.title);

  const groupName = (id: number | null | undefined) =>
    groups.data?.find((g) => g.id === id)?.name ?? "—";
  const termName = (id: number | null | undefined) =>
    terms.data?.find((t) => t.id === id)?.name ?? "";
  const unitTitle = (id: number | null | undefined) =>
    id == null ? "" : (units.data?.find((u) => u.id === id)?.title ?? "");

  return (
    <div>
      <PageHeader
        title="Lessons"
        subtitle="Curriculum units group a term's learning into blocks; lesson plans are the individual sessions inside them (draft → published), each with its own objectives, plan and resources. Press Open on any row to see the whole thing, not just the form."
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

      {tab === "plans" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            A <b>lesson plan</b> is one dated session for one group. It carries the{" "}
            <b>learning objectives</b> (what a child should know or be able to do by
            the end) and the <b>plan</b> itself (the run of the session — starter,
            main activity, plenary, differentiation, assessment, materials), plus
            any attached resources. It starts as <b>Draft</b> and you <b>Publish</b>{" "}
            it when it is final. Click a row to edit the header fields; press{" "}
            <b>Open</b> to read and work on the full plan.
          </p>
          <FilterBar>
            <FilterSelect
              value={planFilter.group}
              onChange={(v) => setPlanFilter((f) => ({ ...f, group: v }))}
              placeholder="All groups"
              options={groupOpts}
            />
            <FilterSelect
              value={planFilter.unit}
              onChange={(v) => setPlanFilter((f) => ({ ...f, unit: v }))}
              placeholder="All units"
              options={unitOpts}
            />
            <FilterSelect
              value={planFilter.term}
              onChange={(v) => setPlanFilter((f) => ({ ...f, term: v }))}
              placeholder="All terms"
              options={termOpts}
            />
            <FilterSelect
              value={planFilter.status}
              onChange={(v) => setPlanFilter((f) => ({ ...f, status: v }))}
              placeholder="All statuses"
              options={STATUS_OPTS}
            />
          </FilterBar>
          <CrudPanel<PlanRow>
            resource="lesson-plans"
            singular="lesson plan"
            query={{
              group: planFilter.group || undefined,
              unit: planFilter.unit || undefined,
              term: planFilter.term || undefined,
              status: planFilter.status || undefined,
            }}
            onRowOpen={setOpenPlan}
            columns={[
              { header: "Title", cell: (r) => r.title },
              { header: "Date", cell: (r) => date(r.date) },
              { header: "Group", cell: (r) => groupName(r.group) },
              { header: "Unit", cell: (r) => unitTitle(r.unit) || "—" },
              {
                header: "Resources",
                cell: (r) => (r.resources?.length ? r.resources.length : "—"),
              },
              {
                header: "Status",
                cell: (r) => (
                  <Badge tone={r.status === "PUBLISHED" ? "green" : "neutral"}>
                    {label(r.status)}
                  </Badge>
                ),
              },
            ]}
            fields={[
              { name: "title", label: "Title", required: true },
              { name: "group", label: "Group", type: "select", required: true, options: groupOpts },
              { name: "unit", label: "Unit", type: "select", options: unitOpts },
              { name: "date", label: "Date", type: "date", required: true },
              {
                name: "objectives",
                label: "Objectives",
                type: "textarea",
                help: "One per line. You can also edit these on Open.",
              },
              {
                name: "body",
                label: "Plan",
                type: "textarea",
                help: "The run of the session. There is more room for this on Open.",
              },
            ]}
          />
        </>
      )}

      {tab === "units" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            A <b>curriculum unit</b> is a block of learning for a group over a term
            — e.g. &ldquo;Numbers to 20&rdquo; or &ldquo;Life cycles&rdquo;. It has
            a <b>summary</b> and a <b>sequence</b> number that orders it against the
            group&apos;s other units. Lesson plans point at a unit so they hang
            together. Press <b>Open</b> to read the summary and see every lesson
            plan filed under it.
          </p>
          <FilterBar>
            <FilterSelect
              value={unitFilter.group}
              onChange={(v) => setUnitFilter((f) => ({ ...f, group: v }))}
              placeholder="All groups"
              options={groupOpts}
            />
            <FilterSelect
              value={unitFilter.term}
              onChange={(v) => setUnitFilter((f) => ({ ...f, term: v }))}
              placeholder="All terms"
              options={termOpts}
            />
          </FilterBar>
          <CrudPanel<UnitRow>
            resource="curriculum-units"
            singular="unit"
            query={{
              group: unitFilter.group || undefined,
              term: unitFilter.term || undefined,
            }}
            onRowOpen={setOpenUnit}
            columns={[
              { header: "Seq", cell: (r) => r.sequence ?? "—" },
              { header: "Title", cell: (r) => r.title },
              { header: "Group", cell: (r) => groupName(r.group) },
              { header: "Term", cell: (r) => termName(r.term) || "—" },
              {
                header: "Lessons",
                cell: (r) => {
                  const n = (plans.data ?? []).filter(
                    (p) => String(p.unit) === String(r.id),
                  ).length;
                  return n ? n : "—";
                },
              },
            ]}
            fields={[
              { name: "title", label: "Title", required: true },
              { name: "group", label: "Group", type: "select", required: true, options: groupOpts },
              { name: "term", label: "Term", type: "select", options: termOpts },
              {
                name: "summary",
                label: "Summary",
                type: "textarea",
                help: "What this block covers. Editable on Open too.",
              },
              {
                name: "sequence",
                label: "Sequence",
                type: "number",
                help: "Orders this unit against the group's others (1, 2, 3 …).",
              },
            ]}
          />
        </>
      )}

      {tab === "resources" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            A <b>resource</b> is a <b>link</b> (URL), a <b>file</b>, or a{" "}
            <b>note</b> (free text), always for a <b>group</b> — either
            attached to one dated lesson (its group fills in automatically),
            or standing on its own for the group generally, like a permission
            slip template or a standing reading list.
          </p>
          <FilterBar>
            <FilterSelect
              value={resourceFilter.group}
              onChange={(v) => setResourceFilter({ group: v })}
              placeholder="All groups"
              options={groupOpts}
            />
          </FilterBar>
          <CrudPanel
            resource="lesson-resources"
            singular="resource"
            query={{ group: resourceFilter.group || undefined }}
            columns={[
              { header: "Title", cell: (r) => r.title as string },
              { header: "Kind", cell: (r) => label(r.kind as string) },
              {
                header: "Group",
                cell: (r) => (r.group_name as string) ?? groupName(r.group as number),
              },
              {
                header: "Lesson plan",
                cell: (r) =>
                  (r.lesson_title as string) ||
                  (r.lesson ? plans.data?.find((p) => p.id === r.lesson)?.title : null) ||
                  "—",
              },
              {
                header: "Link",
                cell: (r) =>
                  r.url ? (
                    <a
                      href={r.url as string}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[var(--campus-accent)] hover:underline"
                    >
                      open
                    </a>
                  ) : (
                    "—"
                  ),
              },
            ]}
            fields={[
              {
                name: "group",
                label: "Group",
                type: "select",
                options: groupOpts,
                help: "Only needed if you don't pick a lesson plan below.",
              },
              {
                name: "lesson",
                label: "Lesson plan",
                type: "select",
                options: planOpts,
                help: "Optional — leave blank for a resource that isn't tied to one dated lesson.",
              },
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
              { name: "url", label: "URL", help: "For a link resource." },
              { name: "body", label: "Note", type: "textarea", help: "For a note resource." },
            ]}
            detailTitle={(r) => `Resource — ${r.title as string}`}
            detailFields={[
              { label: "Title", value: (r) => r.title as string },
              { label: "Kind", value: (r) => label(r.kind as string) },
              {
                label: "Group",
                value: (r) => (r.group_name as string) ?? groupName(r.group as number),
              },
              {
                label: "Lesson plan",
                value: (r) =>
                  (r.lesson_title as string) ||
                  (r.lesson
                    ? (plans.data?.find((p) => p.id === r.lesson)?.title ?? String(r.lesson))
                    : "—"),
              },
              { label: "URL", value: (r) => (r.url as string) || "—" },
              { label: "Note", value: (r) => (r.body as string) || "—", long: true },
            ]}
          />
        </>
      )}

      <LessonPlanDrawer
        plan={openPlan}
        onClose={() => setOpenPlan(null)}
        groupName={groupName(openPlan?.group)}
        unitTitle={unitTitle(openPlan?.unit)}
      />
      <CurriculumUnitDrawer
        unit={openUnit}
        onClose={() => setOpenUnit(null)}
        groupName={groupName(openUnit?.group)}
        termName={termName(openUnit?.term)}
        lessons={plans.data ?? []}
        onJumpToPlan={(p) => {
          setOpenUnit(null);
          setOpenPlan(p);
        }}
      />
    </div>
  );
}

/* ------------------------------------------------------------- plan drawer */

function LessonPlanDrawer({
  plan,
  onClose,
  groupName,
  unitTitle,
}: {
  plan: PlanRow | null;
  onClose: () => void;
  groupName: string;
  unitTitle: string;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [live, setLive] = useState<PlanRow | null>(plan);
  const [objectives, setObjectives] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    setLive(plan);
    setObjectives(plan?.objectives ?? "");
    setBody(plan?.body ?? "");
  }, [plan]);

  if (!plan || !live) return null;

  const published = live.status === "PUBLISHED";
  const dirty =
    objectives !== (live.objectives ?? "") || body !== (live.body ?? "");

  const reloadList = () =>
    qc.invalidateQueries({ queryKey: ["list", "lesson-plans"] });

  async function refresh() {
    if (!plan) return;
    const fresh = await retrieve<PlanRow>("lesson-plans", plan.id);
    setLive(fresh);
    setObjectives(fresh.objectives ?? "");
    setBody(fresh.body ?? "");
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

  const boxClass =
    "w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm text-[var(--campus-fg)]";

  return (
    <Modal open={!!plan} onClose={onClose} title={`Lesson plan — ${live.title}`} wide>
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Badge tone={published ? "green" : "neutral"}>{label(live.status)}</Badge>
          <span className="text-[var(--campus-muted)]">{date(live.date)}</span>
          <span className="text-[var(--campus-muted)]">{groupName}</span>
          {unitTitle && (
            <span className="text-[var(--campus-muted)]">Unit: {unitTitle}</span>
          )}
        </div>

        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
            Learning objectives
          </h3>
          <p className="mb-1.5 text-xs text-[var(--campus-muted)]">
            What a child should know or be able to do by the end of the session.
            One per line.
          </p>
          <textarea
            className={boxClass}
            rows={4}
            value={objectives}
            onChange={(e) => setObjectives(e.target.value)}
            placeholder={
              "Count on from any number within 20\nUse a number line to add two one-digit numbers"
            }
          />
        </section>

        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
            The plan
          </h3>
          <p className="mb-1.5 text-xs text-[var(--campus-muted)]">
            The run of the session: starter / warm-up, the main activity, the
            plenary or wrap-up, how you differentiate for who needs it, how you
            check they got it, and the materials you need.
          </p>
          <textarea
            className={boxClass}
            rows={12}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={
              "Starter (5 min): …\nMain (25 min): …\nPlenary (10 min): …\nDifferentiation: …\nAssessment: …\nMaterials: …"
            }
          />
        </section>

        <div className="flex justify-end">
          <Button
            size="sm"
            variant="subtle"
            disabled={!dirty || busy === "save"}
            onClick={() =>
              withBusy("save", async () => {
                await patch("lesson-plans", plan.id, { objectives, body });
                toast("success", "Saved");
                await refresh();
              })
            }
          >
            {busy === "save" ? "Saving…" : "Save changes"}
          </Button>
        </div>

        <NestedList
          resource="lesson-resources"
          parentKey="lesson"
          parentId={plan.id}
          title="Resources"
          render={(r) => (
            <span>
              <span className="font-medium">{String(r.title ?? "")}</span>
              <span className="text-[var(--campus-muted)]">
                {" "}
                · {label(String(r.kind ?? ""))}
              </span>
              {r.url ? (
                <>
                  {" "}
                  —{" "}
                  <a
                    href={String(r.url)}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[var(--campus-accent)] hover:underline"
                  >
                    open
                  </a>
                </>
              ) : null}
              {r.body ? (
                <span className="text-[var(--campus-muted)]">
                  {" "}
                  — {String(r.body)}
                </span>
              ) : null}
            </span>
          )}
          addFields={[
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
            { name: "url", label: "URL", help: "For a link resource." },
            {
              name: "body",
              label: "Note",
              type: "textarea",
              help: "For a note resource.",
            },
          ]}
        />

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-[var(--campus-line)] pt-3">
          {!published && (
            <Button
              disabled={busy === "publish"}
              onClick={() =>
                withBusy("publish", async () => {
                  await act("lesson-plans", plan.id, "publish");
                  toast("success", "Published");
                  await refresh();
                })
              }
            >
              Publish
            </Button>
          )}
        </div>
        {published && (
          <p className="text-xs text-[var(--campus-muted)]">
            This plan is published — the version of record. You can still adjust it
            here if you need to.
          </p>
        )}
      </div>
    </Modal>
  );
}

/* ------------------------------------------------------------- unit drawer */

function CurriculumUnitDrawer({
  unit,
  onClose,
  groupName,
  termName,
  lessons,
  onJumpToPlan,
}: {
  unit: UnitRow | null;
  onClose: () => void;
  groupName: string;
  termName: string;
  lessons: PlanRow[];
  onJumpToPlan: (p: PlanRow) => void;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [live, setLive] = useState<UnitRow | null>(unit);
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setLive(unit);
    setSummary(unit?.summary ?? "");
  }, [unit]);

  if (!unit || !live) return null;

  const mine = lessons
    .filter((l) => String(l.unit) === String(unit.id))
    .sort((a, b) => a.date.localeCompare(b.date));

  return (
    <Modal
      open={!!unit}
      onClose={onClose}
      title={`Curriculum unit — ${live.title}`}
      wide
    >
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="text-[var(--campus-muted)]">{groupName}</span>
          {termName && (
            <span className="text-[var(--campus-muted)]">{termName}</span>
          )}
          <span className="text-[var(--campus-muted)]">
            Sequence #{live.sequence}
          </span>
        </div>

        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
            Summary
          </h3>
          <p className="mb-1.5 text-xs text-[var(--campus-muted)]">
            What this block of learning covers and roughly how long it runs — the
            umbrella the individual lesson plans sit under.
          </p>
          <textarea
            className="w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm text-[var(--campus-fg)]"
            rows={5}
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
          />
          <div className="mt-1 flex justify-end">
            <Button
              size="sm"
              variant="subtle"
              disabled={busy || summary === (live.summary ?? "")}
              onClick={async () => {
                setBusy(true);
                try {
                  await patch("curriculum-units", unit.id, { summary });
                  toast("success", "Saved");
                  const fresh = await retrieve<UnitRow>(
                    "curriculum-units",
                    unit.id,
                  );
                  setLive(fresh);
                  setSummary(fresh.summary ?? "");
                  qc.invalidateQueries({
                    queryKey: ["list", "curriculum-units"],
                  });
                } catch (e) {
                  toast("error", apiMessage(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              {busy ? "Saving…" : "Save summary"}
            </Button>
          </div>
        </section>

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
            Lesson plans in this unit ({mine.length})
          </h3>
          {mine.length === 0 ? (
            <p className="text-sm text-[var(--campus-muted)]">
              No lesson plans are linked to this unit yet. On the{" "}
              <b>Lesson plans</b> tab, create a plan and pick this unit — or edit
              an existing plan to attach it.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--campus-line)] rounded-md border border-[var(--campus-line)] text-sm">
              {mine.map((l) => (
                <li
                  key={l.id}
                  className="flex items-center justify-between gap-2 px-3 py-2"
                >
                  <span className="min-w-0">
                    <span className="text-[var(--campus-muted)]">
                      {date(l.date)}
                    </span>{" "}
                    — <span className="font-medium">{l.title}</span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    <Badge tone={l.status === "PUBLISHED" ? "green" : "neutral"}>
                      {label(l.status)}
                    </Badge>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => onJumpToPlan(l)}
                    >
                      Open
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </Modal>
  );
}

/* ------------------------------------------------------------------ filters */

function FilterBar({ children }: { children: React.ReactNode }) {
  return <div className="mb-3 flex flex-wrap gap-2">{children}</div>;
}

function FilterSelect({
  value,
  onChange,
  placeholder,
  options: opts,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  options: { value: string | number; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-2.5 py-1.5 text-sm text-[var(--campus-fg)] focus:border-[var(--campus-accent)] focus:outline-none"
    >
      <option value="">{placeholder}</option>
      {opts.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
