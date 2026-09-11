"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getSchoolProfile,
  updateSchoolProfile,
  uploadSchoolLogo,
  clearSchoolLogo,
  uploadSignature,
  clearSignature,
  designatePrincipal,
  type SchoolProfile,
} from "@/lib/school";
import { getSiteConfig, updateSiteConfig, type SiteConfig } from "@/lib/config";
import { whoami } from "@/lib/auth";
import { useAll } from "@/lib/hooks";
import { useToast } from "@/components/Toast";
import { PageHeader, Card, Badge, Button, Spinner, ErrorNote } from "@/components/ui";
import { apiMessage, label } from "@/lib/format";

const INPUT =
  "w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm text-[var(--campus-fg)] transition-colors focus:border-[var(--campus-accent)] focus:outline-none focus:ring-2 focus:ring-[var(--campus-ring)]";

type Draft = Partial<SchoolProfile>;

function Field({
  label,
  value,
  onChange,
  placeholder,
  textarea,
  span2,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  textarea?: boolean;
  span2?: boolean;
}) {
  return (
    <label className={`block ${span2 ? "sm:col-span-2" : ""}`}>
      <span className="mb-1 block text-xs font-medium text-[var(--campus-muted)]">
        {label}
      </span>
      {textarea ? (
        <textarea
          className={INPUT}
          rows={3}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          className={INPUT}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </label>
  );
}

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="p-5">
      <h2 className="text-sm font-semibold">{title}</h2>
      {hint && (
        <p className="mt-0.5 text-xs text-[var(--campus-muted)]">{hint}</p>
      )}
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">{children}</div>
    </Card>
  );
}

function Letterhead({ p }: { p: SchoolProfile }) {
  return (
    <div className="flex items-start gap-4 border-b-2 border-[var(--campus-fg)] pb-3">
      {p.logo_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={p.logo_url}
          alt=""
          className="h-16 w-auto max-w-[160px] object-contain"
        />
      ) : (
        <div className="grid h-16 w-16 shrink-0 place-items-center rounded-md border border-dashed border-[var(--campus-line)] text-[10px] text-[var(--campus-muted)]">
          logo
        </div>
      )}
      <div className="min-w-0">
        <div className="text-lg font-bold leading-tight">
          {p.name || "Your school name"}
        </div>
        {p.address_block && (
          <div className="mt-0.5 whitespace-pre-line text-xs text-[var(--campus-muted)]">
            {p.address_block}
          </div>
        )}
        {(p.phone || p.email || p.website) && (
          <div className="mt-0.5 text-xs text-[var(--campus-muted)]">
            {[p.phone, p.email, p.website].filter(Boolean).join(" · ")}
          </div>
        )}
        {p.motto && (
          <div className="mt-1 text-xs italic text-[var(--campus-muted)]">
            {p.motto}
          </div>
        )}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const sigFileRef = useRef<HTMLInputElement>(null);
  const q = useQuery({ queryKey: ["school"], queryFn: getSchoolProfile });
  const me = useQuery({ queryKey: ["me"], queryFn: whoami });
  const [draft, setDraft] = useState<Draft>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (q.data) setDraft(q.data);
  }, [q.data]);

  if (q.isLoading) return <Spinner />;
  if (q.isError)
    return (
      <div>
        <PageHeader title="School settings" />
        <Card className="p-4">
          <ErrorNote message={apiMessage(q.error)} />
        </Card>
      </div>
    );

  const p = { ...(q.data as SchoolProfile), ...draft } as SchoolProfile;
  const set = (k: keyof SchoolProfile) => (v: string) =>
    setDraft((d) => ({ ...d, [k]: v }));

  const dirty = q.data
    ? (Object.keys(draft) as (keyof SchoolProfile)[]).some(
        (k) => draft[k] !== (q.data as SchoolProfile)[k],
      )
    : false;

  async function save() {
    setBusy(true);
    try {
      const patch: Draft = {};
      const keys: (keyof SchoolProfile)[] = [
        "name", "legal_name", "motto", "address_line1", "address_line2",
        "city", "region", "postal_code", "country", "phone", "email",
        "website", "principal_name", "principal_title", "report_card_footer",
      ];
      for (const k of keys) {
        if (draft[k] !== undefined && draft[k] !== (q.data as SchoolProfile)[k]) {
          (patch as Record<string, unknown>)[k] = draft[k];
        }
      }
      const next = await updateSchoolProfile(patch);
      qc.setQueryData(["school"], next);
      setDraft(next);
      toast("success", "School settings saved");
    } catch (err) {
      toast("error", apiMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function onLogo(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    try {
      const next = await uploadSchoolLogo(file);
      qc.setQueryData(["school"], next);
      setDraft((d) => ({ ...d, logo_url: next.logo_url }));
      toast("success", "Logo updated");
    } catch (err) {
      toast("error", apiMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function removeLogo() {
    setBusy(true);
    try {
      const next = await clearSchoolLogo();
      qc.setQueryData(["school"], next);
      setDraft((d) => ({ ...d, logo_url: null }));
      toast("success", "Logo removed");
    } catch (err) {
      toast("error", apiMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function onSignature(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    try {
      const next = await uploadSignature(file);
      qc.setQueryData(["school"], next);
      setDraft((d) => ({ ...d, has_signature: next.has_signature, signature_url: next.signature_url }));
      toast("success", "Signature saved");
    } catch (err) {
      toast("error", apiMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function removeSignature() {
    setBusy(true);
    try {
      await clearSignature();
      qc.invalidateQueries({ queryKey: ["school"] });
      setDraft((d) => ({ ...d, has_signature: false, signature_url: null }));
      toast("success", "Signature removed");
    } catch (err) {
      toast("error", apiMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="School settings"
        subtitle="Your school's name, contact details and logo. These appear on generated report cards and IEP documents, and in the Campus header."
        actions={
          <Button size="sm" onClick={save} disabled={!dirty || busy}>
            {busy ? "Saving…" : "Save changes"}
          </Button>
        }
      />

      <div className="space-y-5">
        <Card className="p-5">
          <h2 className="text-sm font-semibold">Document letterhead — preview</h2>
          <p className="mt-0.5 text-xs text-[var(--campus-muted)]">
            How the header will look at the top of a report card.
          </p>
          <div className="mt-4 rounded-lg bg-white p-5 text-[#1c2126] shadow-sm">
            <Letterhead p={p} />
          </div>
        </Card>

        <Section
          title="Identity"
          hint="The name shown on documents and in the app."
        >
          <Field label="School name" value={p.name} onChange={set("name")} placeholder="Maple Grove Primary School" />
          <Field label="Legal / district name" value={p.legal_name} onChange={set("legal_name")} />
          <Field label="Motto or tagline" value={p.motto} onChange={set("motto")} span2 />
          <div className="sm:col-span-2">
            <span className="mb-1 block text-xs font-medium text-[var(--campus-muted)]">
              Logo
            </span>
            <div className="flex items-center gap-4">
              {p.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={p.logo_url}
                  alt=""
                  className="h-14 w-auto max-w-[140px] rounded border border-[var(--campus-line)] bg-white object-contain p-1"
                />
              ) : (
                <div className="grid h-14 w-14 place-items-center rounded border border-dashed border-[var(--campus-line)] text-[10px] text-[var(--campus-muted)]">
                  none
                </div>
              )}
              <input
                ref={fileRef}
                type="file"
                accept="image/png,image/jpeg,image/svg+xml,image/webp"
                className="hidden"
                onChange={onLogo}
              />
              <Button size="sm" variant="ghost" onClick={() => fileRef.current?.click()} disabled={busy}>
                {p.logo_url ? "Replace" : "Upload"}
              </Button>
              {p.logo_url && (
                <Button size="sm" variant="ghost" onClick={removeLogo} disabled={busy}>
                  Remove
                </Button>
              )}
            </div>
            <p className="mt-1 text-xs text-[var(--campus-muted)]">
              PNG, JPG, SVG or WebP. Shown at ~72px tall on documents.
            </p>
          </div>
        </Section>

        <Section title="Address">
          <Field label="Address line 1" value={p.address_line1} onChange={set("address_line1")} span2 />
          <Field label="Address line 2" value={p.address_line2} onChange={set("address_line2")} span2 />
          <Field label="City / town" value={p.city} onChange={set("city")} />
          <Field label="State / province" value={p.region} onChange={set("region")} />
          <Field label="Postal / ZIP code" value={p.postal_code} onChange={set("postal_code")} />
          <Field label="Country" value={p.country} onChange={set("country")} />
        </Section>

        <Section title="Contact">
          <Field label="Phone" value={p.phone} onChange={set("phone")} />
          <Field label="Email" value={p.email} onChange={set("email")} />
          <Field label="Website" value={p.website} onChange={set("website")} placeholder="maplegrove.example" />
        </Section>

        <Section
          title="Report cards"
          hint="Signature line and fine print at the bottom of every generated report card."
        >
          <Field label="Principal / head name" value={p.principal_name} onChange={set("principal_name")} />
          <Field label="Title" value={p.principal_title} onChange={set("principal_title")} placeholder="Principal" />
          <Field
            label="Footer text"
            value={p.report_card_footer}
            onChange={set("report_card_footer")}
            textarea
            span2
            placeholder="This report is confidential and intended for the parent or guardian named above."
          />
        </Section>

        <SignatureSection
          p={p}
          me={me.data}
          busy={busy}
          sigFileRef={sigFileRef}
          onSignature={onSignature}
          removeSignature={removeSignature}
          onDraft={setDraft}
        />

        <div className="flex justify-end">
          <Button onClick={save} disabled={!dirty || busy}>
            {busy ? "Saving…" : "Save changes"}
          </Button>
        </div>

        <RegionFees />
      </div>
    </div>
  );
}

function SignatureSection({
  p,
  me,
  busy,
  sigFileRef,
  onSignature,
  removeSignature,
  onDraft,
}: {
  p: SchoolProfile;
  me: { id: string; role: string } | null | undefined;
  busy: boolean;
  sigFileRef: React.RefObject<HTMLInputElement | null>;
  onSignature: (e: React.ChangeEvent<HTMLInputElement>) => void;
  removeSignature: () => void;
  onDraft: (fn: (d: Draft) => Draft) => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const staff = useAll<{ id: string; display_name: string }>("auth/users");
  const [pick, setPick] = useState("");
  const [settingPrincipal, setSettingPrincipal] = useState(false);

  const isSuperadmin = me?.role === "SUPERADMIN";
  const isPrincipal = !!me && me.id === p.principal_user;
  const canSign = isSuperadmin || isPrincipal;

  async function setPrincipal() {
    if (!pick) return;
    setSettingPrincipal(true);
    try {
      const next = await designatePrincipal(pick);
      qc.setQueryData(["school"], next);
      onDraft((d) => ({ ...d, principal_user: next.principal_user, principal_user_name: next.principal_user_name }));
      toast("success", "Principal designated");
      setPick("");
    } catch (err) {
      toast("error", apiMessage(err));
    } finally {
      setSettingPrincipal(false);
    }
  }

  return (
    <Section
      title="Signature"
      hint="Placed on every generated report card. Only the designated principal (or a superadmin) can upload or replace it — this is enforced by the server, not just hidden in the UI."
    >
      <div className="sm:col-span-2 space-y-4">
        {isSuperadmin && (
          <div className="flex flex-wrap items-end gap-2 rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] p-3">
            <label className="min-w-[220px] flex-1">
              <span className="mb-1 block text-xs font-medium text-[var(--campus-muted)]">
                Designated principal
              </span>
              <select
                className="w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] px-3 py-2 text-sm"
                value={pick}
                onChange={(e) => setPick(e.target.value)}
              >
                <option value="">
                  {p.principal_user_name ? `Currently: ${p.principal_user_name}` : "— none set —"}
                </option>
                {(staff.data ?? []).map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.display_name}
                  </option>
                ))}
              </select>
            </label>
            <Button size="sm" onClick={setPrincipal} disabled={!pick || settingPrincipal}>
              {settingPrincipal ? "Saving…" : "Set principal"}
            </Button>
          </div>
        )}

        <div className="flex items-center gap-4">
          {p.signature_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={p.signature_url}
              alt=""
              className="h-14 w-auto max-w-[220px] rounded border border-[var(--campus-line)] bg-white object-contain p-1"
            />
          ) : (
            <div className="grid h-14 w-40 place-items-center rounded border border-dashed border-[var(--campus-line)] text-xs text-[var(--campus-muted)]">
              no signature
            </div>
          )}
          <input
            ref={sigFileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={onSignature}
          />
          {canSign ? (
            <>
              <Button size="sm" variant="ghost" onClick={() => sigFileRef.current?.click()} disabled={busy}>
                {p.signature_url ? "Replace" : "Upload"}
              </Button>
              {p.signature_url && (
                <Button size="sm" variant="ghost" onClick={removeSignature} disabled={busy}>
                  Remove
                </Button>
              )}
            </>
          ) : (
            <p className="text-xs text-[var(--campus-muted)]">
              {p.principal_user_name
                ? `Only ${p.principal_user_name} can update this.`
                : "No principal designated yet — a superadmin can set one above."}
            </p>
          )}
        </div>
      </div>
    </Section>
  );
}

function RegionFees() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["site-config"], queryFn: getSiteConfig });
  const [draft, setDraft] = useState<Partial<SiteConfig>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (q.data) setDraft({});
  }, [q.data]);

  if (q.isLoading || !q.data) return null;
  const c = { ...q.data, ...draft } as SiteConfig;
  const dirty = (Object.keys(draft) as (keyof SiteConfig)[]).some(
    (k) => draft[k] !== q.data![k],
  );

  async function save() {
    setBusy(true);
    try {
      const next = await updateSiteConfig(draft);
      qc.setQueryData(["site-config"], next);
      setDraft({});
      toast("success", "Region settings saved");
    } catch (err) {
      toast("error", apiMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold">Region &amp; fees</h2>
        <Badge tone="neutral">{label(c.deployment_mode)}</Badge>
      </div>
      <p className="mt-0.5 text-xs text-[var(--campus-muted)]">
        Also set by the companion Setup &amp; Configuration tool. Currency locks
        once invoices exist.
      </p>
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field
          label="Country (ISO code)"
          value={c.country}
          onChange={(v) => setDraft((d) => ({ ...d, country: v.toUpperCase() }))}
          placeholder="CA"
        />
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-[var(--campus-muted)]">
            Currency
          </span>
          <select
            className={INPUT}
            value={c.currency}
            disabled={c.currency_locked}
            onChange={(e) => setDraft((d) => ({ ...d, currency: e.target.value }))}
          >
            {c.currency_options.map((o) => (
              <option key={o.code} value={o.code}>
                {o.code} — {o.name}
              </option>
            ))}
          </select>
          {c.currency_locked && (
            <span className="mt-1 block text-xs text-[var(--campus-muted)]">
              Locked — invoices already exist. Change it with the companion tool
              (<code>change_currency --force</code>).
            </span>
          )}
        </label>
        <Field
          label="Locale"
          value={c.locale}
          onChange={(v) => setDraft((d) => ({ ...d, locale: v }))}
          placeholder="en-CA"
        />
        <label className="flex items-end gap-2 pb-2 text-sm">
          <input
            type="checkbox"
            checked={c.collects_fees}
            onChange={(e) =>
              setDraft((d) => ({ ...d, collects_fees: e.target.checked }))
            }
          />
          <span>
            This institution collects tuition / fees
            <span className="block text-xs text-[var(--campus-muted)]">
              Off hides the whole Billing area, on this install and the portal.
            </span>
          </span>
        </label>
      </div>
      <div className="mt-4 flex justify-end">
        <Button onClick={save} disabled={!dirty || busy}>
          {busy ? "Saving…" : "Save region settings"}
        </Button>
      </div>
    </Card>
  );
}
