"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useAll } from "@/lib/hooks";
import { create, remove } from "@/lib/resource";
import { apiMessage } from "@/lib/format";
import { Button, EmptyState, Spinner } from "./ui";
import { Modal, ConfirmButton } from "./Modal";
import { RecordForm, type FieldDef } from "./RecordForm";
import { useToast } from "./Toast";

interface Row {
  id: string | number;
  [k: string]: unknown;
}

/**
 * A compact list of a child resource filtered client-side to one parent
 * (the nested viewsets don't all support ?parent= filtering), with an
 * inline "Add" that pre-sets the parent key.
 */
export function NestedList<T extends Row>({
  resource,
  parentKey,
  parentId,
  title,
  render,
  addFields,
  addFixed,
}: {
  resource: string;
  parentKey: string;
  parentId: string | number;
  title: string;
  render: (row: T) => ReactNode;
  addFields?: FieldDef[];
  addFixed?: Record<string, unknown>;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const q = useAll<T>(resource);
  const rows = (q.data ?? []).filter(
    (r) => String(r[parentKey]) === String(parentId),
  );
  const reload = () => qc.invalidateQueries({ queryKey: ["all", resource] });

  return (
    <div className="rounded-md border border-[var(--campus-line)]">
      <div className="flex items-center justify-between border-b border-[var(--campus-line)] px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-[var(--campus-muted)]">
          {title}
        </span>
        {addFields && (
          <Button size="sm" variant="subtle" onClick={() => setAdding(true)}>
            + Add
          </Button>
        )}
      </div>

      {q.isLoading ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <EmptyState message={`No ${title.toLowerCase()}.`} />
      ) : (
        <ul className="divide-y divide-[var(--campus-line)] text-sm">
          {rows.map((r) => (
            <li
              key={r.id}
              className="flex items-center justify-between gap-2 px-3 py-2"
            >
              <span className="min-w-0">{render(r)}</span>
              <ConfirmButton
                variant="ghost"
                message="Remove this entry?"
                onConfirm={async () => {
                  try {
                    await remove(resource, r.id);
                    toast("success", "Removed");
                    reload();
                  } catch (e) {
                    toast("error", apiMessage(e));
                  }
                }}
              >
                Remove
              </ConfirmButton>
            </li>
          ))}
        </ul>
      )}

      {addFields && (
        <Modal
          open={adding}
          onClose={() => setAdding(false)}
          title={`Add — ${title}`}
        >
          <RecordForm
            fields={addFields}
            submitLabel="Add"
            onSubmit={async (values) => {
              const merged: Record<string, unknown> = {
                ...values,
                [parentKey]: parentId,
                ...addFixed,
              };
              const hasFile = Object.values(merged).some(
                (v) => typeof File !== "undefined" && v instanceof File,
              );
              if (hasFile) {
                const fd = new FormData();
                for (const [k, v] of Object.entries(merged)) {
                  if (v == null || v === "") continue;
                  fd.append(k, v instanceof File ? v : String(v));
                }
                await create(resource, fd);
              } else {
                await create(resource, merged);
              }
              toast("success", "Added");
              setAdding(false);
              reload();
            }}
            onCancel={() => setAdding(false)}
          />
        </Modal>
      )}
    </div>
  );
}
