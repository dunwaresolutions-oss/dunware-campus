"use client";

import { useState } from "react";
import { useAll, useList, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import { create, act } from "@/lib/resource";
import { PageHeader, Tabs, Badge, Button, Card, Spinner } from "@/components/ui";
import { Modal } from "@/components/Modal";
import { RecordForm } from "@/components/RecordForm";
import { useToast } from "@/components/Toast";
import { money, date, apiMessage, label } from "@/lib/format";
import { useQueryClient } from "@tanstack/react-query";

export default function BillingPage() {
  const [tab, setTab] = useState("invoices");
  const students = useAll<{ id: string; display_name: string }>("students");
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
        subtitle="Fee schedules, invoices, and a manual mark-paid workflow. No card handling — payments record a cash / cheque / e-transfer reference."
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
        <Invoices
          studentOpts={studentOpts}
          guardianOpts={guardianOpts}
          termOpts={termOpts}
          students={students.data ?? []}
        />
      )}

      {tab === "fees" && (
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
        />
      )}

      {tab === "payments" && (
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
        />
      )}

      {tab === "credits" && (
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
  students: { id: string; display_name: string }[];
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [detail, setDetail] = useState<{ id: number } | null>(null);
  const q = useList<{
    id: number;
    student: string;
    status: string;
    total_cents: number;
    balance_cents: number;
    due_date: string | null;
  }>("invoices", { page });
  const reload = () => qc.invalidateQueries({ queryKey: ["list", "invoices"] });

  async function run(id: number, verb: string, body?: Record<string, unknown>) {
    try {
      await act("invoices", id, verb, body);
      toast("success", `${label(verb)} done`);
      reload();
    } catch (e) {
      toast("error", apiMessage(e));
    }
  }

  return (
    <Card>
      <div className="flex justify-end border-b border-neutral-100 p-3">
        <Button size="sm" onClick={() => setCreating(true)}>
          New invoice
        </Button>
      </div>
      {q.isLoading ? (
        <Spinner />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-200 text-left text-xs uppercase text-neutral-500">
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
              <tr key={inv.id} className="border-b border-neutral-100">
                <td className="px-3 py-2.5">
                  {students.find((s) => s.id === inv.student)?.display_name ??
                    inv.student}
                </td>
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
                  <span className="flex justify-end gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setDetail({ id: inv.id })}
                    >
                      Lines
                    </Button>
                    {inv.status === "DRAFT" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => run(inv.id, "issue")}
                      >
                        Issue
                      </Button>
                    )}
                    {inv.status !== "PAID" && inv.status !== "VOID" && (
                      <>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            const amt = window.prompt(
                              `Payment amount in dollars (balance ${money(
                                inv.balance_cents,
                              )}):`,
                            );
                            if (!amt) return;
                            const method =
                              window.prompt(
                                "Method (CASH / CHEQUE / E_TRANSFER / OTHER):",
                                "E_TRANSFER",
                              ) || "OTHER";
                            const reference =
                              window.prompt("Reference:") || "";
                            run(inv.id, "mark-paid", {
                              amount_cents: Math.round(Number(amt) * 100),
                              method,
                              reference,
                            });
                          }}
                        >
                          Mark paid
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            const reason = window.prompt("Void reason:") || "";
                            run(inv.id, "void", { reason });
                          }}
                        >
                          Void
                        </Button>
                      </>
                    )}
                  </span>
                </td>
              </tr>
            ))}
            {(q.data?.results ?? []).length === 0 && (
              <tr>
                <td colSpan={6} className="p-6 text-center text-neutral-500">
                  No invoices yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
      <div className="flex justify-between p-3 text-xs text-neutral-500">
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

      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title="New invoice"
      >
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

      {detail && (
        <InvoiceLines invoiceId={detail.id} onClose={() => setDetail(null)} />
      )}
    </Card>
  );
}

function InvoiceLines({
  invoiceId,
  onClose,
}: {
  invoiceId: number;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const lines = useList<{
    id: number;
    description: string;
    quantity: number;
    unit_amount_cents: number;
    amount_cents: number;
  }>("invoice-lines", { invoice: invoiceId });
  const [adding, setAdding] = useState(false);

  return (
    <Modal open onClose={onClose} title={`Invoice #${invoiceId} — lines`} wide>
      <div className="space-y-3">
        <table className="w-full text-sm">
          <tbody>
            {(lines.data?.results ?? []).map((l) => (
              <tr key={l.id} className="border-b border-neutral-100">
                <td className="py-2">{l.description}</td>
                <td className="py-2 text-right">{l.quantity}</td>
                <td className="py-2 text-right">
                  {money(l.unit_amount_cents)}
                </td>
                <td className="py-2 text-right font-medium">
                  {money(l.amount_cents)}
                </td>
              </tr>
            ))}
            {(lines.data?.results ?? []).length === 0 && (
              <tr>
                <td className="py-3 text-neutral-500">No lines.</td>
              </tr>
            )}
          </tbody>
        </table>
        {adding ? (
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
              qc.invalidateQueries({ queryKey: ["list", "invoice-lines"] });
              qc.invalidateQueries({ queryKey: ["list", "invoices"] });
            }}
            onCancel={() => setAdding(false)}
          />
        ) : (
          <Button size="sm" onClick={() => setAdding(true)}>
            Add line
          </Button>
        )}
      </div>
    </Modal>
  );
}
