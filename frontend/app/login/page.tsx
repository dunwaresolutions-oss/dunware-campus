"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { isStaff, login } from "@/lib/auth";

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

  return (
    <main className="mx-auto max-w-sm px-6 py-24">
      <h1 className="text-xl font-semibold">Sign in to Campus</h1>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        <input
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
        />
        <input
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        <input
          className="w-full rounded-md border border-neutral-300 px-3 py-2"
          placeholder="Authenticator code (staff)"
          value={otp}
          onChange={(e) => setOtp(e.target.value)}
          inputMode="numeric"
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          className="w-full rounded-md bg-sky-700 px-4 py-2 text-white hover:bg-sky-800 disabled:opacity-50"
          disabled={busy}
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
