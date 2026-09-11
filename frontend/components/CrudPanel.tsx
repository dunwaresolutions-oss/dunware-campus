"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
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
import { RecordDetail, type DetailField } from "./RecordDetail";
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
  detailFields,
  detailTitle,
  onRowOpen,
  searchable,
  searchPlaceholder,
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
  /** built-in read-only preview: row-click opens it, edit moves to a button */
  detailFields?: DetailField[];
  detailTitle?: (row: T) => string;
  /** bespoke preview: row-click calls this instead of opening the edit form */
  onRowOpen?: (row: T) => void;
  /** show a debounced "?q=" search box in the header — the resource's
   *  viewset must support it (see backend `?q=` filters per app). */
  searchable?: boolean;
  searchPlaceholder?: string;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<T | null>(null);
  const [creating, setCreating] = useState(false);
  const [detail, setDetail] = useState<T | null>(null);
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const id = setTimeout(() => setDebounced(term.trim()), 300);
    return () => clearTimeout(id);
  }, [term]);
  useEffect(() => {
    setPage(1);
  }, [debounced]);

  const q = useList<T>(resource, {
    ...query,
    page,
    ...(searchable ? { q: debounced || undefined } : {}),
  });
  const reload = () =>
    qc.invalidateQueries({ queryKey: ["list", resource] });

  // Row-click opens the preview when there is one; edit becomes a button.
  const rowOpensPreview = !!(onRowOpen || detailFields);
  const showEditButton = rowOpensPreview && canEdit && !!fields;

  const cols: Column<T>[] = [...columns];
  if (canDelete || extraRowActions || showEditButton) {
    cols.push({
      header: "",
      className: "text-right whitespace-nowrap",
      cell: (row) => (
        <span
          className="flex justify-end gap-1"
          onClick={(e) => e.stopPropagation()}
        >
          {extraRowActions?.(row, reload)}
          {showEditButton && (
            <Button size="sm" variant="ghost" onClick={() => setEditing(row)}>
              Edit
            </Button>
          )}
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
      {(searchable || ((canCreate || headerActions) && fields)) && (
        <div className="flex items-center justify-between gap-2 border-b border-[var(--campus-line)] p-3">
          {searchable ? (
            <input
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder={searchPlaceholder ?? `Search ${singular}s…`}
              className="w-full max-w-xs rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-1.5 text-sm text-[var(--campus-fg)] focus:border-[var(--campus-accent)] focus:outline-none"
            />
          ) : (
            <span />
          )}
          <span className="flex items-center gap-2">
            {headerActions}
            {canCreate && fields && (
              <Button size="sm" onClick={() => setCreating(true)}>
                New {singular}
              </Button>
            )}
          </span>
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
              onRowOpen
                ? (row) => onRowOpen(row)
                : detailFields
                  ? (row) => setDetail(row)
                  : canEdit && fields
                    ? (row) => setEditing(row)
                    : undefined
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

      {detailFields && (
        <Modal
          open={!!detail}
          onClose={() => setDetail(null)}
          title={
            detail && detailTitle
              ? detailTitle(detail)
              : `${singular[0].toUpperCase()}${singular.slice(1)}`
          }
          wide
        >
          {detail && (
            <div className="space-y-4">
              <RecordDetail
                fields={detailFields}
                row={detail as Record<string, unknown>}
              />
              {(canEdit && fields) || canDelete ? (
                <div className="flex justify-end gap-2 border-t border-[var(--campus-line)] pt-3">
                  {canEdit && fields && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setEditing(detail);
                        setDetail(null);
                      }}
                    >
                      Edit
                    </Button>
                  )}
                  {canDelete && (
                    <ConfirmButton
                      variant="ghost"
                      message={`Delete this ${singular}?`}
                      onConfirm={async () => {
                        try {
                          await remove(resource, detail.id);
                          toast("success", `${singular} deleted`);
                          setDetail(null);
                          reload();
                        } catch (err) {
                          toast("error", apiMessage(err));
                        }
                      }}
                    >
                      Delete
                    </ConfirmButton>
                  )}
                </div>
              ) : null}
            </div>
          )}
        </Modal>
      )}
    </Card>
  );
}
