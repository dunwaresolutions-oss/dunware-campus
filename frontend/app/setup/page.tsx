"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createFirstAdmin, setupStatus } from "@/lib/auth";
import { Button, Card, ErrorNote } from "@/components/ui";
import { apiMessage } from "@/lib/format";

export default function SetupPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErr, setFieldErr] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setupStatus().then((s) => {
      if (!s.needs_setup) router.replace("/login/");
      else setReady(true);
    });
  }, [router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErr({});
    if (password !== confirm) {
      setFieldErr({ confirm: "The two passwords do not match." });
      return;
    }
    setBusy(true);
    try {
      await createFirstAdmin({ username: username.trim(), email: email.trim(), password });
      router.replace("/mfa/");
    } catch (err) {
      const body = (err as { body?: unknown })?.body;
      if (body && typeof body === "object" && !Array.isArray(body)) {
        const fe: Record<string, string> = {};
        for (const [k, v] of Object.entries(body as Record<string, unknown>)) {
          if (k === "detail") continue;
          fe[k] = Array.isArray(v) ? v.join(" ") : String(v);
        }
        setFieldErr(fe);
      }
      setError(apiMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const field =
    "w-full rounded-lg border border-[var(--campus-line)] bg-[var(--campus-input-bg)] text-[var(--campus-fg)] px-3 py-2.5 text-sm transition-colors focus:border-[var(--campus-accent)] focus:outline-none focus:ring-2 focus:ring-[var(--campus-ring)]";

  if (!ready) return null;

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
            <h1 className="text-lg font-semibold tracking-tight">Welcome to Campus</h1>
            <p className="text-sm text-[var(--campus-muted)]">
              Create the administrator account for this install
            </p>
          </div>
        </div>

        <Card className="p-6 shadow-[var(--campus-shadow-md)]">
          <form onSubmit={onSubmit} className="space-y-3.5">
            <div>
              <input
                className={field}
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
              />
              {fieldErr.username && (
                <p className="mt-1 text-xs text-red-600">{fieldErr.username}</p>
              )}
            </div>
            <div>
              <input
                className={field}
                type="email"
                placeholder="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
              {fieldErr.email && (
                <p className="mt-1 text-xs text-red-600">{fieldErr.email}</p>
              )}
            </div>
            <div>
              <input
                className={field}
                type="password"
                placeholder="Password (12+ characters)"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
              {fieldErr.password && (
                <p className="mt-1 text-xs text-red-600">{fieldErr.password}</p>
              )}
            </div>
            <div>
              <input
                className={field}
                type="password"
                placeholder="Confirm password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
              />
              {fieldErr.confirm && (
                <p className="mt-1 text-xs text-red-600">{fieldErr.confirm}</p>
              )}
            </div>
            {error && <ErrorNote message={error} />}
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "Creating…" : "Create administrator"}
            </Button>
            <p className="text-center text-xs text-[var(--campus-muted)]">
              Next you&apos;ll set up an authenticator app — staff accounts need it
              before they can reach any records.
            </p>
          </form>
        </Card>
      </div>
    </main>
  );
}
