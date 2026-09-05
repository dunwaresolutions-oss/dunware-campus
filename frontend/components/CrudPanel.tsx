"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useList } from "@/lib/hooks";
import { create, patch, remove } from "@/lib/resource";
import { apiMessage } from "@/lib/format";
import {
  Button,
  Card,
  ErrorNote,
  Paginator,
  Spinner,
  Table,
  type Column,
} from "./ui";
import { Modal, ConfirmButton } from "./Modal";
import { RecordForm, type FieldDef } from "./RecordForm";
import { useToast } from "./Toast";

type Row = { id: string | number; [k: string]: unknown };

export function CrudPanel<T extends { id: string | number } = Row>({
  resource,
  columns,
  fields,
  singular,
  query,
  canCreate = true,
  canEdit = true,
  canDelete = true,
  toInitial,
  fromForm,
  extraRowActions,
  headerActions,
  emptyText,
}: {
  resource: string;
  columns: Column<T>[];
  fields?: FieldDef[];
  singular: string;
  query?: Record<string, string | number | boolean | undefined>;
  canCreate?: boolean;
  canEdit?: boolean;
  canDelete?: boolean;
  /** map a row to form initial values (defaults to the row itself) */
  toInitial?: (row: T) => Record<string, unknown>;
  /** map submitted form values to the request body */
  fromForm?: (values: Record<string, unknown>) => Record<string, unknown>;
  extraRowActions?: (row: T, reload: () => void) => ReactNode;
  headerActions?: ReactNode;
  emptyText?: string;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<T | null>(null);
  const [creating, setCreating] = useState(false);

  const q = useList<T>(resource, { ...query, page });
  const reload = () =>
    qc.invalidateQueries({ queryKey: ["list", resource] });

  const cols: Column<T>[] = [...columns];
  if (canDelete || extraRowActions) {
    cols.push({
      header: "",
      className: "text-right whitespace-nowrap",
      cell: (row) => (
        <span
          className="flex justify-end gap-1"
          onClick={(e) => e.stopPropagation()}
        >
          {extraRowActions?.(row, reload)}
          {canDelete && (
            <ConfirmButton
              variant="ghost"
              message={`Delete this ${singular}?`}
              onConfirm={async () => {
                try {
                  await remove(resource, row.id);
                  toast("success", `${singular} deleted`);
                  reload();
                } catch (err) {
                  toast("error", apiMessage(err));
                }
              }}
            >
              Delete
            </ConfirmButton>
          )}
        </span>
      ),
    });
  }

  async function save(values: Record<string, unknown>) {
    const body = fromForm ? fromForm(values) : values;
    if (editing) {
      await patch(resource, editing.id, body);
      toast("success", `${singular} updated`);
    } else {
      await create(resource, body);
      toast("success", `${singular} created`);
    }
    setEditing(null);
    setCreating(false);
    reload();
  }

  return (
    <Card>
      {(canCreate || headerActions) && fields && (
        <div className="flex justify-end gap-2 border-b border-neutral-100 p-3">
          {headerActions}
          {canCreate && (
            <Button size="sm" onClick={() => setCreating(true)}>
              New {singular}
            </Button>
          )}
        </div>
      )}

      {q.isLoading ? (
        <Spinner />
      ) : q.isError ? (
        <div className="p-4">
          <ErrorNote message={apiMessage(q.error)} />
        </div>
      ) : (
        <>
          <Table
            columns={cols}
            rows={q.data?.results ?? []}
            empty={emptyText ?? `No ${singular} records yet.`}
            onRowClick={
              canEdit && fields ? (row) => setEditing(row) : undefined
            }
          />
          <Paginator
            page={page}
            count={q.data?.count ?? 0}
            onPage={setPage}
          />
        </>
      )}

      {fields && (
        <Modal
          open={creating || !!editing}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
          title={editing ? `Edit ${singular}` : `New ${singular}`}
        >
          <RecordForm
            fields={fields}
            initialValues={
              editing
                ? toInitial
                  ? toInitial(editing)
                  : (editing as Record<string, unknown>)
                : {}
            }
            submitLabel={editing ? "Save changes" : `Create ${singular}`}
            onSubmit={save}
            onCancel={() => {
              setCreating(false);
              setEditing(null);
            }}
          />
        </Modal>
      )}
    </Card>
  );
}
