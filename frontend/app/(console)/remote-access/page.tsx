"use client";

import { useQuery } from "@tanstack/react-query";
import { remoteAccessStatus } from "@/lib/remoteAccess";
import { PageHeader, Card, Spinner, Badge, ErrorNote } from "@/components/ui";
import { apiMessage } from "@/lib/format";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-[var(--campus-line)] py-2.5 last:border-0">
      <span className="text-sm text-[var(--campus-muted)]">{label}</span>
      <span className="text-right text-sm font-medium">{children}</span>
    </div>
  );
}

export default function RemoteAccessPage() {
  const q = useQuery({
    queryKey: ["remote-access-status"],
    queryFn: remoteAccessStatus,
    refetchInterval: 30_000,
  });

  return (
    <div>
      <PageHeader
        title="Remote access"
        subtitle="Off-premises access to Campus. Read-only here — a technician turns it on or off on the box with deploy\\remote-setup.ps1."
      />

      {q.isLoading ? (
        <Spinner />
      ) : q.isError ? (
        <Card>
          <div className="p-4">
            <ErrorNote message={apiMessage(q.error)} />
          </div>
        </Card>
      ) : (
        <div className="space-y-4">
          <Card>
            <div className="p-4">
              <Row label="Status">
                {q.data!.enabled ? (
                  <Badge tone="green">On</Badge>
                ) : (
                  <Badge tone="neutral">Off — LAN only</Badge>
                )}
              </Row>
              <Row label="Method">{q.data!.mode}</Row>
              <Row label="Public address">
                {q.data!.hosts.length ? q.data!.hosts.join(", ") : "—"}
              </Row>
              <Row label="Real-client-IP header">
                {q.data!.client_ip_header || "—"}
              </Row>
              <Row label="Tunnel service (Campus Remote)">
                <Badge tone={q.data!.service === "RUNNING" ? "green" : "neutral"}>
                  {q.data!.service}
                </Badge>
              </Row>
            </div>
          </Card>

          <Card>
            <div className="p-4">
              <Row label="Build">
                {q.data!.build.version}
                {q.data!.build.git ? ` (${q.data!.build.git})` : ""}
                {q.data!.build.frozen ? "" : " · dev"}
              </Row>
              <Row label="Active hotfixes">
                {q.data!.hotfixes.length ? (
                  <span className="text-[var(--campus-amber,#b45309)]">
                    {q.data!.hotfixes.join(", ")}
                  </span>
                ) : (
                  "none"
                )}
              </Row>
            </div>
          </Card>

          <p className="text-xs text-[var(--campus-muted)]">{q.data!.manage_hint}</p>
          <p className="text-xs text-[var(--campus-muted)]">
            Data at rest never leaves this box in any mode. In Cloudflare Tunnel
            mode, connections pass through Cloudflare&rsquo;s network in transit —
            see docs/REMOTE_ACCESS_AND_YOUR_DATA.md.
          </p>
        </div>
      )}
    </div>
  );
}
