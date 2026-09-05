"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { inviteStaff, listUsers } from "@/lib/auth";
import { useAll, options } from "@/lib/hooks";
import { CrudPanel } from "@/components/CrudPanel";
import {
  PageHeader,
  Tabs,
  Card,
  Badge,
  Spinner,
  ErrorNote,
} from "@/components/ui";
import { RecordForm } from "@/components/RecordForm";
import { useToast } from "@/components/Toast";
import { label, apiMessage } from "@/lib/format";

const INVITE_ROLES = ["ADMIN", "TEACHER", "TUTOR", "FRONT_DESK"];

export default function StaffPage() {
  const [tab, setTab] = useState("directory");
  const toast = useToast();
  const users = useQuery({ queryKey: ["users"], queryFn: listUsers });
  const groups = useAll<{ id: number; name: string }>("groups");
  const [invite, setInvite] = useState<{ token: string; email: string } | null>(
    null,
  );

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
        <Card>
          {users.isLoading ? (
            <Spinner />
          ) : users.isError ? (
            <div className="p-4">
              <ErrorNote message={apiMessage(users.error)} />
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--campus-line)] text-left text-xs uppercase text-[var(--campus-muted)]">
                  <th className="px-3 py-2 font-medium">Username</th>
                  <th className="px-3 py-2 font-medium">Email</th>
                  <th className="px-3 py-2 font-medium">Role</th>
                  <th className="px-3 py-2 font-medium">Active</th>
                </tr>
              </thead>
              <tbody>
                {(users.data ?? []).map((u) => (
                  <tr key={u.id} className="border-b border-[var(--campus-line)]">
                    <td className="px-3 py-2.5 font-medium">{u.username}</td>
                    <td className="px-3 py-2.5">{u.email || "—"}</td>
                    <td className="px-3 py-2.5">{label(u.role)}</td>
                    <td className="px-3 py-2.5">
                      {u.is_active ? (
                        <Badge tone="green">Active</Badge>
                      ) : (
                        <Badge tone="red">Disabled</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
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
