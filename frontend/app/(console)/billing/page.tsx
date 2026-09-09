"use client";

import { useEffect, useState } from "react";
import { useAll, useList, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { ActionButton } from "@/components/ActionButton";
import { create, act, retrieve } from "@/lib/resource";
import { PageHeader, Tabs, Badge, Button, Card, Spinner } from "@/components/ui";
import { Modal } from "@/components/Modal";
import { RecordForm } from "@/components/RecordForm";
import { useToast } from "@/components/Toast";
import { money, date, datetime, label, apiMessage, yn } from "@/lib/format";
import { useQueryClient } from "@tanstack/react-query";

interface Student {
  id: string;
  display_name: string;
}

export default function BillingPage() {
  const [tab, setTab] = useState("invoices");
  const students = useAll<Student>("students");
  const guardians = useAll<{ id: number; first_name: string; last_name: string }>(
    "guardians",
  );
  const terms = useAll<{ id: number; name: string }>("terms");
  const groups = useAll<{ id: number; name: string }>("groups");
  const studentOpts = options(students.data, (s) => s.display_name);
  const guardianOpts = options(
    guardians.data,
    (g) => `${g.first_name} ${g.last_name}`,
  );
  const termOpts = options(terms.data, (t) => t.name);
  const groupOpts = options(groups.data, (g) => g.name);

  return (
    <div>
      <PageHeader
        title="Billing"
        subtitle="Per-family invoices built from your standard charges, a manual mark-paid workflow, and a read-only ledger. No card handling — a payment records a cash / cheque / e-transfer reference you took elsewhere. Press Open on an invoice for its lines, payments and running balance."
      />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "invoices", label: "Invoices" },
          { key: "fees", label: "Fee schedules" },
          { key: "payments", label: "Payments" },
          { key: "credits", label: "Credits" },
        ]}
      />

      {tab === "invoices" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            An <b>invoice</b> starts as a <b>Draft</b> (invisible to the family,
            owes nothing). Add charge lines, then <b>Issue</b> — that dates it and
            shows it on the portal. <b>Mark paid</b> records a payment and
            re-totals the balance; <b>Void</b> cancels an issued invoice with a
            reason (it is kept, never deleted). Press <b>Open</b> for the full
            picture.
          </p>
          <Invoices
            studentOpts={studentOpts}
            guardianOpts={guardianOpts}
            termOpts={termOpts}
            students={students.data ?? []}
          />
        </>
      )}

      {tab === "fees" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            A <b>fee schedule</b> is a template for a standard charge (term fee,
            monthly fee, one-off). It is not a bill — you copy a line from it onto
            a per-family invoice.
          </p>
          <CrudPanel
            resource="fee-schedules"
            singular="fee schedule"
            columns={[
              { header: "Name", cell: (r) => r.name as string },
              { header: "Amount", cell: (r) => money(r.amount_cents as number) },
              { header: "Frequency", cell: (r) => label(r.frequency as string) },
              {
                header: "Group",
                cell: (r) =>
                  groups.data?.find((g) => g.id === r.group)?.name ?? "Any",
              },
            ]}
            fields={[
              { name: "name", label: "Name", required: true },
              { name: "description", label: "Description" },
              { name: "amount_cents", label: "Amount", type: "money", required: true },
              {
                name: "frequency",
                label: "Frequency",
                type: "select",
                options: ["ONE_TIME", "MONTHLY", "TERM", "ANNUAL"].map((v) => ({
                  value: v,
                  label: label(v),
                })),
              },
              { name: "group", label: "Group (optional)", type: "select", options: groupOpts },
              { name: "active", label: "Active", type: "checkbox" },
            ]}
            detailTitle={(r) => `Fee schedule — ${r.name as string}`}
            detailFields={[
              { label: "Name", value: (r) => r.name as string },
              { label: "Amount", value: (r) => money(r.amount_cents as number) },
              { label: "Frequency", value: (r) => label(r.frequency as string) },
              {
                label: "Group",
                value: (r) =>
                  r.group
                    ? (groups.data?.find((g) => g.id === r.group)?.name ?? "one group")
                    : "Any group",
              },
              { label: "Active", value: (r) => yn(r.active) },
              {
                label: "Description",
                value: (r) => (r.description as string) || "—",
                long: true,
              },
            ]}
          />
        </>
      )}

      {tab === "payments" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            The <b>payments</b> ledger is every payment recorded, read-only.
            Payments are only ever created through an invoice&apos;s <b>Mark
            paid</b> action.
          </p>
          <CrudPanel
            resource="payments"
            singular="payment"
            canCreate={false}
            canEdit={false}
            canDelete={false}
            columns={[
              { header: "Invoice", cell: (r) => `#${r.invoice}` },
              { header: "Amount", cell: (r) => money(r.amount_cents as number) },
              { header: "Method", cell: (r) => label(r.method as string) },
              { header: "Reference", cell: (r) => (r.reference as string) || "—" },
              { header: "Received", cell: (r) => date(r.received_at as string) },
            ]}
            detailTitle={(r) => `Payment — ${money(r.amount_cents as number)}`}
            detailFields={[
              { label: "Invoice", value: (r) => `#${r.invoice}` },
              { label: "Amount", value: (r) => money(r.amount_cents as number) },
              { label: "Method", value: (r) => label(r.method as string) },
              { label: "Reference", value: (r) => (r.reference as string) || "—" },
              {
                label: "Received",
                value: (r) =>
                  r.received_at ? datetime(r.received_at as string) : "—",
              },
              { label: "Note", value: (r) => (r.note as string) || "—", long: true },
            ]}
          />
        </>
      )}

      {tab === "credits" && (
        <>
          <p className="mb-3 text-sm text-[var(--campus-muted)]">
            A <b>credit</b> is a manual adjustment in the family&apos;s favour.
            There is no automated refund path — a credit is how money owed back is
            represented.
          </p>
          <CrudPanel
            resource="credits"
            singular="credit"
            columns={[
              {
                header: "Student",
                cell: (r) =>
                  students.data?.find((s) => s.id === r.student)?.display_name ??
                  r.student,
              },
              { header: "Amount", cell: (r) => money(r.amount_cents as number) },
              { header: "Reason", cell: (r) => (r.reason as string) || "—" },
            ]}
            fields={[
              { name: "student", label: "Student", type: "select", required: true, options: studentOpts },
              { name: "amount_cents", label: "Amount", type: "money", required: true },
              { name: "reason", label: "Reason", required: true },
            ]}
          />
        </>
      )}
    </div>
  );
}

function Invoices({
  studentOpts,
  guardianOpts,
  termOpts,
  students,
}: {
  studentOpts: { value: string | number; label: string }[];
  guardianOpts: { value: string | number; label: string }[];
  termOpts: { value: string | number; label: string }[];
  students: Student[];
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);
  const q = useList<{
    id: number;
    student: string;
    status: string;
    total_cents: number;
    balance_cents: number;
    due_date: string | null;
  }>("invoices", { page });
  const reload = () => qc.invalidateQueries({ queryKey: ["list", "invoices"] });
  const studentName = (id: string) =>
    students.find((s) => s.id === id)?.display_name ?? id;

  return (
    <Card>
      <div className="flex justify-end border-b border-[var(--campus-line)] p-3">
        <Button size="sm" onClick={() => setCreating(true)}>
          New invoice
        </Button>
      </div>
      {q.isLoading ? (
        <Spinner />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--campus-line)] text-left text-xs uppercase text-[var(--campus-muted)]">
              <th className="px-3 py-2 font-medium">Student</th>
              <th className="px-3 py-2 font-medium">Total</th>
              <th className="px-3 py-2 font-medium">Balance</th>
              <th className="px-3 py-2 font-medium">Due</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(q.data?.results ?? []).map((inv) => (
              <tr
                key={inv.id}
                onClick={() => setDetailId(inv.id)}
                className="cursor-pointer border-b border-[var(--campus-line)] transition-colors hover:bg-[var(--campus-accent-soft)]/60"
              >
                <td className="px-3 py-2.5">{studentName(inv.student)}</td>
                <td className="px-3 py-2.5">{money(inv.total_cents)}</td>
                <td className="px-3 py-2.5">{money(inv.balance_cents)}</td>
                <td className="px-3 py-2.5">{date(inv.due_date)}</td>
                <td className="px-3 py-2.5">
                  <Badge
                    tone={
                      inv.status === "PAID"
                        ? "green"
                        : inv.status === "VOID"
                          ? "neutral"
                          : "amber"
                    }
                  >
                    {label(inv.status)}
                  </Badge>
                </td>
                <td className="px-3 py-2.5 text-right">
                  <span
                    className="flex justify-end gap-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {inv.status === "DRAFT" && (
                      <ActionButton
                        label="Issue"
                        confirm="Issue this invoice? It can't be edited after."
                        onRun={() => act("invoices", inv.id, "issue")}
                        onDone={reload}
                      />
                    )}
                    {inv.status !== "PAID" && inv.status !== "VOID" && (
                      <>
                        <ActionButton
                          label="Mark paid"
                          title={`Record a payment · balance ${money(inv.balance_cents)}`}
                          fields={[
                            { name: "amount_cents", label: "Amount", type: "money", required: true },
                            {
                              name: "method",
                              label: "Method",
                              type: "select",
                              required: true,
                              options: ["CASH", "CHEQUE", "E_TRANSFER", "OTHER"].map(
                                (v) => ({ value: v, label: label(v) }),
                              ),
                            },
                            { name: "reference", label: "Reference" },
                            { name: "note", label: "Note" },
                          ]}
                          onRun={(v) => act("invoices", inv.id, "mark-paid", v)}
                          onDone={reload}
                        />
                        <ActionButton
                          label="Void"
                          variant="ghost"
                          title="Void this invoice"
                          fields={[{ name: "reason", label: "Reason", required: true }]}
                          onRun={(v) => act("invoices", inv.id, "void", v)}
                          onDone={reload}
                        />
                      </>
                    )}
                  </span>
                </td>
              </tr>
            ))}
            {(q.data?.results ?? []).length === 0 && (
              <tr>
                <td colSpan={6} className="p-6 text-center text-[var(--campus-muted)]">
                  No invoices yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
      <div className="flex justify-between p-3 text-xs text-[var(--campus-muted)]">
        <span>{q.data?.count ?? 0} total</span>
        <span className="flex gap-1">
          <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Prev
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={!q.data?.next}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </span>
      </div>

      <Modal open={creating} onClose={() => setCreating(false)} title="New invoice">
        <RecordForm
          fields={[
            { name: "student", label: "Student", type: "select", required: true, options: studentOpts },
            { name: "guardian", label: "Billed to (guardian)", type: "select", options: guardianOpts },
            { name: "term", label: "Term", type: "select", options: termOpts },
            { name: "due_date", label: "Due date", type: "date" },
            { name: "notes", label: "Notes", type: "textarea" },
          ]}
          submitLabel="Create draft"
          onSubmit={async (v) => {
            await create("invoices", v);
            toast("success", "Draft invoice created");
            setCreating(false);
            reload();
          }}
          onCancel={() => setCreating(false)}
        />
      </Modal>

      <InvoiceDetail
        invoiceId={detailId}
        onClose={() => setDetailId(null)}
        studentName={studentName}
        onChanged={reload}
      />
    </Card>
  );
}

interface InvoiceFull {
  id: number;
  student: string;
  status: string;
  issued_at: string | null;
  due_date: string | null;
  notes: string;
  total_cents: number;
  paid_cents: number;
  balance_cents: number;
  lines: {
    id: number;
    description: string;
    quantity: number;
    unit_amount_cents: number;
    amount_cents: number;
  }[];
  payments: {
    id: number;
    amount_cents: number;
    method: string;
    reference: string;
    received_at: string;
    note: string;
  }[];
}

function InvoiceDetail({
  invoiceId,
  onClose,
  studentName,
  onChanged,
}: {
  invoiceId: number | null;
  onClose: () => void;
  studentName: (id: string) => string;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [inv, setInv] = useState<InvoiceFull | null>(null);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);

  async function load() {
    if (invoiceId == null) return;
    setLoading(true);
    try {
      setInv(await retrieve<InvoiceFull>("invoices", invoiceId));
    } catch (e) {
      toast("error", apiMessage(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setInv(null);
    if (invoiceId != null) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [invoiceId]);

  if (invoiceId == null) return null;

  const editable = inv?.status === "DRAFT";

  return (
    <Modal open onClose={onClose} title={`Invoice #${invoiceId}`} wide>
      {loading || !inv ? (
        <Spinner />
      ) : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <Badge
              tone={
                inv.status === "PAID"
                  ? "green"
                  : inv.status === "VOID"
                    ? "neutral"
                    : "amber"
              }
            >
              {label(inv.status)}
            </Badge>
            <span className="text-[var(--campus-muted)]">
              {studentName(inv.student)}
            </span>
            {inv.issued_at && (
              <span className="text-[var(--campus-muted)]">
                issued {date(inv.issued_at)}
              </span>
            )}
            {inv.due_date && (
              <span className="text-[var(--campus-muted)]">
                due {date(inv.due_date)}
              </span>
            )}
          </div>

          <div className="flex gap-6 text-sm">
            <div>
              <div className="text-xs uppercase tracking-wide text-[var(--campus-muted)]">
                Total
              </div>
              <div className="text-base font-semibold">{money(inv.total_cents)}</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-[var(--campus-muted)]">
                Paid
              </div>
              <div className="text-base font-semibold">{money(inv.paid_cents)}</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-[var(--campus-muted)]">
                Balance
              </div>
              <div className="text-base font-semibold">
                {money(inv.balance_cents)}
              </div>
            </div>
          </div>

          {inv.notes && (
            <p className="whitespace-pre-wrap rounded-md bg-black/[0.03] p-3 text-sm dark:bg-white/[0.04]">
              {inv.notes}
            </p>
          )}

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
              Lines ({inv.lines.length})
            </h3>
            {inv.lines.length === 0 ? (
              <p className="text-sm text-[var(--campus-muted)]">No lines yet.</p>
            ) : (
              <table className="w-full text-sm">
                <tbody>
                  {inv.lines.map((l) => (
                    <tr
                      key={l.id}
                      className="border-b border-[var(--campus-line)] last:border-0"
                    >
                      <td className="py-2">{l.description}</td>
                      <td className="py-2 text-right text-[var(--campus-muted)]">
                        {l.quantity} × {money(l.unit_amount_cents)}
                      </td>
                      <td className="py-2 text-right font-medium">
                        {money(l.amount_cents)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {editable ? (
              adding ? (
                <div className="mt-3">
                  <RecordForm
                    fields={[
                      { name: "description", label: "Description", required: true },
                      { name: "quantity", label: "Quantity", type: "number" },
                      { name: "unit_amount_cents", label: "Unit amount", type: "money", required: true },
                    ]}
                    submitLabel="Add line"
                    onSubmit={async (v) => {
                      await create("invoice-lines", { ...v, invoice: invoiceId });
                      toast("success", "Line added");
                      setAdding(false);
                      await load();
                      onChanged();
                    }}
                    onCancel={() => setAdding(false)}
                  />
                </div>
              ) : (
                <Button size="sm" className="mt-3" onClick={() => setAdding(true)}>
                  Add line
                </Button>
              )
            ) : (
              <p className="mt-2 text-xs text-[var(--campus-muted)]">
                Lines can only be changed while the invoice is a draft.
              </p>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
              Payments ({inv.payments.length})
            </h3>
            {inv.payments.length === 0 ? (
              <p className="text-sm text-[var(--campus-muted)]">
                Nothing recorded. Use <b>Mark paid</b> on the invoice row.
              </p>
            ) : (
              <ul className="divide-y divide-[var(--campus-line)] rounded-md border border-[var(--campus-line)] text-sm">
                {inv.payments.map((p) => (
                  <li
                    key={p.id}
                    className="flex items-center justify-between gap-2 px-3 py-2"
                  >
                    <span>
                      <span className="font-medium">{money(p.amount_cents)}</span>{" "}
                      <span className="text-[var(--campus-muted)]">
                        · {label(p.method)}
                        {p.reference ? ` · ${p.reference}` : ""}
                      </span>
                    </span>
                    <span className="text-xs text-[var(--campus-muted)]">
                      {date(p.received_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </Modal>
  );
}
