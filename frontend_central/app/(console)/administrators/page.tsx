"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addDistrictAssignment,
  inviteAdministrator,
  listDirectory,
  listDistrictAssignments,
  removeDistrictAssignment,
  type DirectoryUser,
} from "@/lib/administrators";
import { whoami, type Role } from "@/lib/auth";
import { useToast } from "@/components/Toast";
import { apiMessage, label } from "@/lib/format";
import { Badge, Button, Card, ErrorNote, PageHeader, Spinner } from "@/components/ui";

const INVITABLE_ROLES: Role[] = ["MINISTRY_ADMIN", "MINISTRY_ANALYST", "DISTRICT_OFFICER"];

function InviteForm({ onDone }: { onDone: () => void }) {
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("DISTRICT_OFFICER");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [invite, setInvite] = useState<{ token: string; email: string } | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setInvite(null);
    try {
      const result = await inviteAdministrator({ email: email.trim(), role });
      toast("success", "Invite created");
      setInvite({ token: result.token, email: result.email });
      setEmail("");
      onDone();
    } catch (err) {
      setError(apiMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const field =
    "w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm";

  return (
    <Card className="p-5">
      <h2 className="mb-3 text-sm font-semibold">Invite a Ministry account</h2>
      <p className="mb-3 text-sm text-[var(--campus-muted)]">
        This generates a one-time token. There is no outbound email from Central itself — copy
        the link below and send it to them directly. They set their own username and password,
        then enrol an authenticator app.
      </p>
      <form onSubmit={onSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <input
          className={field}
          type="email"
          placeholder="Email address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <select
          className={field}
          value={role}
          onChange={(e) => setRole(e.target.value as Role)}
        >
          {INVITABLE_ROLES.map((r) => (
            <option key={r} value={r}>
              {label(r)}
            </option>
          ))}
        </select>
        <Button type="submit" disabled={busy || !email.trim()}>
          {busy ? "Creating…" : "Create invite"}
        </Button>
        {error && (
          <div className="sm:col-span-3">
            <ErrorNote message={error} />
          </div>
        )}
      </form>
      {invite && (
        <div className="mt-4 rounded-xl border border-[var(--glass-border)] bg-[var(--campus-accent-soft)] p-4 text-sm">
          <div className="font-medium text-[var(--campus-accent-strong)]">
            Invite for {invite.email} — shown once
          </div>
          <div className="mt-2">
            <span className="text-[var(--campus-muted)]">Redeem link: </span>
            <code className="break-all">
              {typeof window !== "undefined" ? window.location.origin : ""}
              /invite/?token={invite.token}
            </code>
          </div>
        </div>
      )}
    </Card>
  );
}

function DistrictRow({ user }: { user: DirectoryUser }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [district, setDistrict] = useState("");

  const assignments = useQuery({
    queryKey: ["district-assignments", user.id],
    queryFn: () => listDistrictAssignments(user.id),
  });

  async function onAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!district.trim()) return;
    setAdding(true);
    try {
      await addDistrictAssignment(user.id, district.trim());
      setDistrict("");
      qc.invalidateQueries({ queryKey: ["district-assignments", user.id] });
    } catch (err) {
      toast("error", apiMessage(err));
    } finally {
      setAdding(false);
    }
  }

  async function onRemove(id: string) {
    try {
      await removeDistrictAssignment(id);
      qc.invalidateQueries({ queryKey: ["district-assignments", user.id] });
    } catch (err) {
      toast("error", apiMessage(err));
    }
  }

  return (
    <div className="mt-2 border-t border-[var(--campus-line)] pt-2">
      <div className="flex flex-wrap items-center gap-2">
        {assignments.data?.map((a) => (
          <Badge key={a.id} tone="sky">
            {a.district}
            <button
              onClick={() => onRemove(a.id)}
              className="ml-1.5 text-[var(--campus-muted)] hover:text-[var(--campus-fg)]"
              aria-label={`Remove ${a.district}`}
            >
              ×
            </button>
          </Badge>
        ))}
        {(!assignments.data || assignments.data.length === 0) && (
          <span className="text-xs text-[var(--campus-muted)]">No districts assigned — sees nothing.</span>
        )}
      </div>
      <form onSubmit={onAdd} className="mt-2 flex gap-2">
        <input
          className="rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-2 py-1 text-xs"
          placeholder="Add district…"
          value={district}
          onChange={(e) => setDistrict(e.target.value)}
        />
        <Button type="submit" variant="ghost" disabled={adding || !district.trim()}>
          Add
        </Button>
      </form>
    </div>
  );
}

export default function AdministratorsPage() {
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: whoami });
  const canManage = me?.role === "MINISTRY_ADMIN" || me?.role === "SUPERADMIN";

  const directory = useQuery({ queryKey: ["directory"], queryFn: listDirectory });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Administrators"
        subtitle="Every Ministry account on this install, and which district(s) each District Officer can see."
      />

      {canManage && <InviteForm onDone={() => directory.refetch()} />}

      <Card className="p-5">
        <h2 className="mb-2 text-sm font-semibold">Accounts ({directory.data?.length ?? 0})</h2>
        {directory.isLoading ? (
          <Spinner />
        ) : directory.isError ? (
          <ErrorNote message={apiMessage(directory.error)} />
        ) : (
          <ul className="divide-y divide-[var(--campus-line)] text-sm">
            {(directory.data ?? []).map((u) => (
              <li key={u.id} className="py-3">
                <div className="flex items-center justify-between">
                  <span>
                    {u.display_name || u.username}
                    <span className="ml-2 text-xs text-[var(--campus-muted)]">{u.email}</span>
                  </span>
                  <div className="flex items-center gap-2">
                    <Badge tone={u.is_active ? "green" : "neutral"}>{label(u.role)}</Badge>
                  </div>
                </div>
                {u.role === "DISTRICT_OFFICER" && canManage && <DistrictRow user={u} />}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
