"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { inviteStaff, listUsers, type DirectoryUser, type Role } from "@/lib/auth";
import { useAll, useQueryParam, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import {
  PageHeader,
  Tabs,
  Card,
  Badge,
  Spinner,
  ErrorNote,
  Table,
  type Column,
} from "@/components/ui";
import { RecordForm } from "@/components/RecordForm";
import { useToast } from "@/components/Toast";
import { api } from "@/lib/api";
import { label, apiMessage } from "@/lib/format";
import { useQueryClient } from "@tanstack/react-query";

const INVITE_ROLES = ["ADMIN", "TEACHER", "TUTOR", "FRONT_DESK"];
const DIRECTORY_ROLES: Role[] = ["SUPERADMIN", "ADMIN", "FRONT_DESK", "TEACHER", "TUTOR"];
const STAFF_STATUSES = [
  "ACTIVE", "SICK_LEAVE", "ON_LEAVE", "SEDENTARY_DUTY",
  "TRANSFERRED", "SUSPENDED", "TERMINATED",
];
const statusTone = (s: string) =>
  s === "ACTIVE" ? "green" : s === "TERMINATED" || s === "SUSPENDED" ? "red" : "amber";

interface Assignment {
  id: string | number;
  user: string;
  group: number;
  role: string;
  active: boolean;
}

export default function StaffPage() {
  const [tab, setTab] = useState("directory");
  const paramTab = useQueryParam("tab");
  useEffect(() => {
    if (paramTab) setTab(paramTab);
  }, [paramTab]);
  const toast = useToast();
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: listUsers });
  const reloadUsers = () => qc.invalidateQueries({ queryKey: ["users"] });
  const groups = useAll<{ id: number; name: string }>("groups");
  const assignments = useAll<Assignment>("group-staff");
  const [invite, setInvite] = useState<{ token: string; email: string } | null>(
    null,
  );
  const [term, setTerm] = useState("");
  const [roleFilter, setRoleFilter] = useState("");

  const groupsFor = (userId: string): string[] =>
    (assignments.data ?? [])
      .filter((a) => a.user === userId && a.active)
      .map((a) => groups.data?.find((g) => g.id === a.group)?.name)
      .filter((n): n is string => !!n);

  const directory = useMemo(() => {
    const q = term.trim().toLowerCase();
    return (users.data ?? []).filter((u) => {
      if (roleFilter && u.role !== roleFilter) return false;
      if (!q) return true;
      return (
        u.username.toLowerCase().includes(q) ||
        u.display_name.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q)
      );
    });
  }, [users.data, term, roleFilter]);

  const directoryColumns: Column<DirectoryUser>[] = [
    {
      header: "Name",
      cell: (u) => (
        <span>
          <span className="font-medium text-[var(--campus-fg)]">
            {u.display_name || u.username}
          </span>
          {u.display_name && u.display_name !== u.username && (
            <span className="ml-1.5 text-xs text-[var(--campus-muted)]">
              @{u.username}
            </span>
          )}
        </span>
      ),
    },
    { header: "Email", cell: (u) => u.email || "—" },
    { header: "Role", cell: (u) => <Badge>{label(u.role)}</Badge> },
    {
      header: "Groups",
      cell: (u) => {
        const g = groupsFor(u.id);
        return g.length ? g.join(", ") : "—";
      },
    },
    {
      header: "Login",
      cell: (u) =>
        u.is_active ? (
          <Badge tone="green">Active</Badge>
        ) : (
          <Badge tone="red">Disabled</Badge>
        ),
    },
    {
      header: "Status",
      cell: (u) => (
        <StaffStatusPicker user={u} onChanged={reloadUsers} />
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Staff"
        subtitle="Invite colleagues, see the directory, and assign teachers / assistants to groups (which is what controls the students and classes they can see)."
      />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "directory", label: "Directory" },
          { key: "invite", label: "Invite" },
          { key: "assignments", label: "Group assignments" },
        ]}
      />

      {tab === "directory" && (
        <>
          <div className="mb-3 flex flex-wrap gap-2">
            <input
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder="Search by name, username or email…"
              className="w-full max-w-xs rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-1.5 text-sm text-[var(--campus-fg)] focus:border-[var(--campus-accent)] focus:outline-none"
            />
            <select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              className="rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-2.5 py-1.5 text-sm text-[var(--campus-fg)] focus:border-[var(--campus-accent)] focus:outline-none"
            >
              <option value="">All roles</option>
              {DIRECTORY_ROLES.map((r) => (
                <option key={r} value={r}>
                  {label(r)}
                </option>
              ))}
            </select>
          </div>
          <Card>
            {users.isLoading ? (
              <Spinner />
            ) : users.isError ? (
              <div className="p-4">
                <ErrorNote message={apiMessage(users.error)} />
              </div>
            ) : (
              <Table
                columns={directoryColumns}
                rows={directory}
                empty={
                  term || roleFilter
                    ? "No one matches this search."
                    : "No staff accounts yet — invite one below."
                }
              />
            )}
          </Card>
        </>
      )}

      {tab === "invite" && (
        <Card className="p-5">
          <p className="mb-4 max-w-lg text-sm text-[var(--campus-muted)]">
            An invite generates a one-time token. On an on-site install there
            may be no outbound email — copy the token and the link below and
            give them to the new staff member directly. They set their own
            username and password, then enrol an authenticator app.
          </p>
          <RecordForm
            fields={[
              { name: "email", label: "Their email", required: true },
              {
                name: "role",
                label: "Role",
                type: "select",
                required: true,
                options: INVITE_ROLES.map((r) => ({
                  value: r,
                  label: label(r),
                })),
              },
            ]}
            submitLabel="Create invite"
            onSubmit={async (v) => {
              const res = await inviteStaff(
                v.email as string,
                v.role as string,
              );
              setInvite({ token: res.token, email: res.email });
              toast("success", "Invite created");
            }}
            onCancel={() => setInvite(null)}
          />
          {invite && (
            <div className="mt-5 rounded-xl border border-[var(--glass-border)] bg-[var(--campus-accent-soft)] p-4 text-sm">
              <div className="font-medium text-[var(--campus-accent-strong)]">
                Invite for {invite.email}
              </div>
              <div className="mt-2">
                <span className="text-[var(--campus-muted)]">Redeem link: </span>
                <code className="break-all">
                  {typeof window !== "undefined" ? window.location.origin : ""}
                  /invite/?token={invite.token}
                </code>
              </div>
              <div className="mt-1">
                <span className="text-[var(--campus-muted)]">Token: </span>
                <code className="break-all">{invite.token}</code>
              </div>
            </div>
          )}
        </Card>
      )}

      {tab === "assignments" && (
        <CrudPanel
          resource="group-staff"
          singular="assignment"
          detailTitle={() => "Group assignment"}
          detailFields={[
            {
              label: "Group",
              value: (r) =>
                groups.data?.find((g) => g.id === r.group)?.name ?? String(r.group),
            },
            {
              label: "Staff member",
              value: (r) =>
                users.data?.find((u) => u.id === String(r.user))?.username ??
                String(r.user),
            },
            { label: "Role in group", value: (r) => label(r.role as string) },
            { label: "Active", value: (r) => (r.active ? "Yes" : "No") },
          ]}
          columns={[
            {
              header: "Group",
              cell: (r) =>
                groups.data?.find((g) => g.id === r.group)?.name ?? r.group,
            },
            {
              header: "Staff",
              cell: (r) =>
                users.data?.find((u) => u.id === String(r.user))?.username ??
                r.user,
            },
            { header: "Role", cell: (r) => label(r.role as string) },
            {
              header: "Active",
              cell: (r) => (r.active ? <Badge tone="green">Yes</Badge> : "No"),
            },
          ]}
          fields={[
            {
              name: "group",
              label: "Group",
              type: "select",
              required: true,
              options: options(groups.data, (g) => g.name),
            },
            {
              name: "user",
              label: "Staff member",
              type: "select",
              required: true,
              options: (users.data ?? [])
                .filter((u) => u.is_active)
                .map((u) => ({
                  value: u.id,
                  label: `${u.username} (${label(u.role)})`,
                })),
            },
            {
              name: "role",
              label: "Role in this group",
              type: "select",
              options: ["LEAD", "ASSISTANT"].map((v) => ({
                value: v,
                label: label(v),
              })),
            },
            { name: "active", label: "Active", type: "checkbox" },
          ]}
        />
      )}
    </div>
  );
}

function StaffStatusPicker({
  user,
  onChanged,
}: {
  user: DirectoryUser;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function change(next: string) {
    if (next === user.status) return;
    setBusy(true);
    try {
      await api(`/auth/users/${user.id}/status/`, {
        method: "PATCH",
        body: JSON.stringify({ status: next }),
      });
      toast("success", `${user.display_name || user.username} marked ${label(next)}`);
      onChanged();
    } catch (e) {
      toast("error", apiMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="flex items-center gap-1.5">
      <Badge tone={statusTone(user.status)}>{label(user.status)}</Badge>
      <select
        value={user.status}
        disabled={busy}
        onChange={(e) => change(e.target.value)}
        className="rounded-md border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-1.5 py-1 text-xs text-[var(--campus-fg)]"
        aria-label={`Change status for ${user.display_name || user.username}`}
      >
        {STAFF_STATUSES.map((s) => (
          <option key={s} value={s}>
            {label(s)}
          </option>
        ))}
      </select>
    </span>
  );
}
