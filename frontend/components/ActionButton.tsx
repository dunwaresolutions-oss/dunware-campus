"use client";

import { useState, type ReactNode } from "react";
import { Button } from "./ui";
import { Modal } from "./Modal";
import { RecordForm, type FieldDef } from "./RecordForm";
import { useToast } from "./Toast";
import { apiMessage } from "@/lib/format";

/**
 * A row/toolbar button that either fires an action directly or, when `fields`
 * are given, opens a small modal form first. Replaces the old window.prompt
 * pattern — no more typing UUIDs by hand.
 */
export function ActionButton({
  label,
  title,
  fields,
  confirm,
  onRun,
  onDone,
  variant = "ghost",
  size = "sm",
}: {
  label: ReactNode;
  title?: string;
  fields?: FieldDef[];
  confirm?: string;
  onRun: (values: Record<string, unknown>) => Promise<unknown>;
  onDone?: () => void;
  variant?: "primary" | "ghost" | "danger" | "subtle";
  size?: "sm" | "md";
}) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function fire(values: Record<string, unknown>) {
    setBusy(true);
    try {
      await onRun(values);
      toast("success", `${typeof label === "string" ? label : "Done"} ✓`);
      setOpen(false);
      onDone?.();
    } catch (e) {
      toast("error", apiMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button
        size={size}
        variant={variant}
        disabled={busy}
        onClick={() => {
          if (fields && fields.length) return setOpen(true);
          if (confirm && !window.confirm(confirm)) return;
          fire({});
        }}
      >
        {label}
      </Button>
      {fields && (
        <Modal
          open={open}
          onClose={() => setOpen(false)}
          title={title ?? (typeof label === "string" ? label : "Action")}
        >
          <RecordForm
            fields={fields}
            submitLabel={typeof label === "string" ? label : "Run"}
            onSubmit={fire}
            onCancel={() => setOpen(false)}
          />
        </Modal>
      )}
    </>
  );
}
