"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAll } from "@/lib/hooks";
import { create, patch, remove } from "@/lib/resource";
import {
  previewTemplate,
  tokenPalette,
  type MessageTemplate,
} from "@/lib/templates";
import { Card, Button, Badge, Spinner } from "@/components/ui";
import { ConfirmButton } from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { apiMessage, datetime, label } from "@/lib/format";

const INPUT =
  "w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm text-[var(--campus-fg)] focus:border-[var(--campus-accent)] focus:outline-none focus:ring-2 focus:ring-[var(--campus-ring)]";

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function MessageTemplates() {
  const qc = useQueryClient();
  const toast = useToast();
  const all = useAll<MessageTemplate>("message-templates");
  const [selId, setSelId] = useState<number | null>(null);

  const templates = useMemo(() => all.data ?? [], [all.data]);
  const sel = templates.find((t) => t.id === selId) ?? null;

  useEffect(() => {
    if (!sel && templates.length) setSelId(templates[0].id);
  }, [templates, sel]);

  async function addTemplate() {
    try {
      const t = await create<MessageTemplate>("message-templates", {
        key: `template-${Date.now().toString(36)}`,
        name: "New template",
        kind: "GENERAL",
        subject: "",
        body: "",
      });
      await qc.invalidateQueries({ queryKey: ["all", "message-templates"] });
      setSelId(t.id);
    } catch (e) {
      toast("error", apiMessage(e));
    }
  }

  if (all.isLoading) return <Spinner />;

  const byKind = templates.reduce<Record<string, MessageTemplate[]>>((acc, t) => {
    (acc[t.kind] ??= []).push(t);
    return acc;
  }, {});

  return (
    <>
      <p className="mb-3 text-sm text-[var(--campus-muted)]">
        The email Campus sends for each event. Drop in{" "}
        <code>[[MERGE_FIELDS]]</code> from the palette — they fill in per
        recipient when the email goes out. The active template of each kind is
        the one used; system templates can be edited but not deleted.
      </p>
      <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
        <Card className="h-max p-2">
          <div className="flex justify-end p-1">
            <Button size="sm" variant="ghost" onClick={addTemplate}>
              + New
            </Button>
          </div>
          {Object.entries(byKind).map(([kind, list]) => (
            <div key={kind} className="mb-2">
              <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
                {label(kind)}
              </div>
              {list.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setSelId(t.id)}
                  className={`flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm ${
                    t.id === selId
                      ? "bg-[var(--campus-accent-soft)] text-[var(--campus-accent)]"
                      : "hover:bg-black/[0.03] dark:hover:bg-white/[0.04]"
                  }`}
                >
                  <span className="min-w-0 truncate">{t.name}</span>
                  {!t.active && <span className="text-[10px] text-[var(--campus-muted)]">off</span>}
                </button>
              ))}
            </div>
          ))}
        </Card>

        {sel ? (
          <TemplateEditor key={sel.id} template={sel} onChanged={() => qc.invalidateQueries({ queryKey: ["all", "message-templates"] })} onDeleted={() => { setSelId(null); qc.invalidateQueries({ queryKey: ["all", "message-templates"] }); }} />
        ) : (
          <Card className="p-6 text-sm text-[var(--campus-muted)]">
            Select a template, or create one.
          </Card>
        )}
      </div>
    </>
  );
}

function TemplateEditor({
  template,
  onChanged,
  onDeleted,
}: {
  template: MessageTemplate;
  onChanged: () => void;
  onDeleted: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState(template.name);
  const [subject, setSubject] = useState(template.subject);
  const [body, setBody] = useState(template.body);
  const [active, setActive] = useState(template.active);
  const [busy, setBusy] = useState(false);

  const subjectRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const lastFocus = useRef<"subject" | "body">("body");

  const palette = useQuery({
    queryKey: ["token-palette", template.kind],
    queryFn: () => tokenPalette(template.kind),
    staleTime: 60_000,
  });

  const dSubject = useDebounced(subject, 400);
  const dBody = useDebounced(body, 400);
  const preview = useQuery({
    queryKey: ["template-preview", template.id, dSubject, dBody],
    queryFn: () => previewTemplate(template.id, dSubject, dBody),
  });

  const dirty =
    name !== template.name ||
    subject !== template.subject ||
    body !== template.body ||
    active !== template.active;

  function insert(tokenName: string) {
    const tok = `[[${tokenName}]]`;
    if (lastFocus.current === "subject") {
      const el = subjectRef.current;
      const at = el?.selectionStart ?? subject.length;
      setSubject(subject.slice(0, at) + tok + subject.slice(at));
      requestAnimationFrame(() => {
        el?.focus();
        el?.setSelectionRange(at + tok.length, at + tok.length);
      });
    } else {
      const el = bodyRef.current;
      const at = el?.selectionStart ?? body.length;
      setBody(body.slice(0, at) + tok + body.slice(at));
      requestAnimationFrame(() => {
        el?.focus();
        el?.setSelectionRange(at + tok.length, at + tok.length);
      });
    }
  }

  async function save() {
    setBusy(true);
    try {
      await patch("message-templates", template.id, { name, subject, body, active });
      toast("success", "Template saved");
      onChanged();
    } catch (e) {
      toast("error", apiMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-2">
          <input
            className={`${INPUT} max-w-xs`}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Badge tone="neutral">{label(template.kind)}</Badge>
          {template.is_system && <Badge tone="sky">system</Badge>}
          <label className="ml-auto flex items-center gap-1.5 text-xs text-[var(--campus-muted)]">
            <input
              type="checkbox"
              checked={active}
              onChange={(e) => setActive(e.target.checked)}
            />
            Active
          </label>
        </div>
        {template.description && (
          <p className="mt-2 text-xs text-[var(--campus-muted)]">
            {template.description}
          </p>
        )}

        <label className="mt-4 block text-xs font-medium text-[var(--campus-muted)]">
          Subject
        </label>
        <input
          ref={subjectRef}
          className={`${INPUT} mt-1`}
          value={subject}
          onFocus={() => (lastFocus.current = "subject")}
          onChange={(e) => setSubject(e.target.value)}
        />

        <label className="mt-3 block text-xs font-medium text-[var(--campus-muted)]">
          Body
        </label>
        <textarea
          ref={bodyRef}
          className={`${INPUT} mt-1 font-[inherit]`}
          rows={10}
          value={body}
          onFocus={() => (lastFocus.current = "body")}
          onChange={(e) => setBody(e.target.value)}
        />

        <div className="mt-3">
          <div className="mb-1 text-xs font-medium text-[var(--campus-muted)]">
            Merge fields — click to insert at the cursor
          </div>
          {palette.isLoading ? (
            <Spinner />
          ) : (
            <div className="space-y-1.5">
              {(palette.data ?? []).map((g) => (
                <div key={g.group} className="flex flex-wrap items-center gap-1">
                  <span className="mr-1 text-[10px] uppercase tracking-wide text-[var(--campus-muted)]">
                    {g.group}
                  </span>
                  {g.tokens.map((t) => (
                    <button
                      key={t.name}
                      onClick={() => insert(t.name)}
                      title={`${t.label} — e.g. ${t.example}`}
                      className="rounded border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-1.5 py-0.5 font-mono text-[11px] hover:border-[var(--campus-accent)] hover:text-[var(--campus-accent)]"
                    >
                      {t.name}
                    </button>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="mt-4 flex items-center gap-2 border-t border-[var(--campus-line)] pt-3">
          <Button onClick={save} disabled={!dirty || busy}>
            {busy ? "Saving…" : "Save"}
          </Button>
          {!template.is_system && (
            <ConfirmButton
              message={`Delete "${template.name}"?`}
              onConfirm={async () => {
                try {
                  await remove("message-templates", template.id);
                  toast("success", "Template deleted");
                  onDeleted();
                } catch (e) {
                  toast("error", apiMessage(e));
                }
              }}
            >
              Delete
            </ConfirmButton>
          )}
          <span className="ml-auto text-xs text-[var(--campus-muted)]">
            updated {datetime(template.updated_at)}
          </span>
        </div>
      </Card>

      <Card className="p-4">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
          Preview — sample data
        </div>
        {preview.isLoading ? (
          <Spinner />
        ) : preview.isError ? (
          <p className="text-sm text-red-600">{apiMessage(preview.error)}</p>
        ) : (
          <div className="rounded-lg bg-white p-4 text-sm text-[#1c2126] shadow-sm">
            <div className="border-b border-neutral-200 pb-2 font-semibold">
              {preview.data?.subject || (
                <span className="text-neutral-400">(no subject)</span>
              )}
            </div>
            <pre className="mt-2 whitespace-pre-wrap font-[inherit]">
              {preview.data?.body}
            </pre>
          </div>
        )}
      </Card>
    </div>
  );
}
