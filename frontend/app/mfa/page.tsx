"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { mfaConfirm, mfaSetup, mfaStatus, type MfaSetup } from "@/lib/auth";
import { Button, Card, ErrorNote } from "@/components/ui";

export default function MfaPage() {
  const router = useRouter();
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [alreadyEnrolled, setAlreadyEnrolled] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const s = await mfaStatus();
        if (s.mfa_verified) {
          router.replace("/");
          return;
        }
        if (s.mfa_enrolled) {
          // device exists — just needs this session verified
          setAlreadyEnrolled(true);
        } else {
          setSetup(await mfaSetup());
        }
      } catch {
        setError("Could not start MFA setup — try signing in again.");
      }
    })();
  }, [router]);

  async function confirm(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await mfaConfirm(code.trim());
      router.replace("/");
    } catch {
      setError("That code didn't match. Check the time on your phone and retry.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-md px-6 py-16">
      <h1 className="text-xl font-semibold">Two-factor authentication</h1>
      <p className="mt-2 text-sm text-neutral-600">
        {alreadyEnrolled
          ? "Enter the current 6-digit code from your authenticator app to finish signing in."
          : "Scan this with Google Authenticator, Authy, or 1Password, then enter the 6-digit code it shows."}
      </p>

      <Card className="mt-6 p-5">
        {setup && (
          <div className="mb-4 flex flex-col items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={setup.qr} alt="MFA QR code" className="h-44 w-44" />
            <code className="rounded bg-neutral-100 px-2 py-1 text-xs">
              {setup.secret}
            </code>
          </div>
        )}
        <form onSubmit={confirm} className="space-y-4">
          <input
            className="w-full rounded-md border border-neutral-300 px-3 py-2 text-center text-lg tracking-widest"
            placeholder="123456"
            inputMode="numeric"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          {error && <ErrorNote message={error} />}
          <Button type="submit" disabled={busy || code.length < 6} className="w-full">
            {busy ? "Verifying…" : "Verify"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
