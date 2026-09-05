"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { isStaff, login } from "@/lib/auth";
import { Button, Card, ErrorNote } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await login(username, password, otp || undefined);
      if (isStaff(me.role)) {
        const needsMfa =
          me.mfa_enrollment_required || (me.must_use_mfa && !me.mfa_verified);
        router.push(needsMfa ? "/mfa/" : "/");
      } else {
        router.push("/portal/");
      }
    } catch (err) {
      setError(
        (err as Error).name === "MfaRequiredError"
          ? "Enter the 6-digit code from your authenticator app."
          : "Invalid username or password.",
      );
    } finally {
      setBusy(false);
    }
  }

  const field =
    "w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] text-[var(--campus-fg)] px-3 py-2.5 text-sm transition-colors focus:border-[var(--campus-accent)] focus:outline-none focus:ring-2 focus:ring-[var(--campus-ring)]";

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <div className="campus-enter w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <Image
            src="/icon.png"
            alt="Campus"
            width={56}
            height={56}
            className="rounded-xl shadow-[var(--campus-shadow-md)]"
          />
          <div>
            <h1 className="text-lg font-semibold tracking-tight">
              Sign in to Campus
            </h1>
            <p className="text-sm text-[var(--campus-muted)]">
              On-site school &amp; daycare operations
            </p>
          </div>
        </div>

        <Card className="p-6 shadow-[var(--campus-shadow-md)]">
          <form onSubmit={onSubmit} className="space-y-3.5">
            <input
              className={field}
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
            />
            <input
              className={field}
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
            <input
              className={field}
              placeholder="Authenticator code (staff)"
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
              inputMode="numeric"
            />
            {error && <ErrorNote message={error} />}
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </Card>
      </div>
    </main>
  );
}
