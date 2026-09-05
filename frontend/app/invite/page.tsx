"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { acceptInvite } from "@/lib/auth";
import { Button, Card, ErrorNote } from "@/components/ui";
import { apiMessage } from "@/lib/format";

function AcceptForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [token, setToken] = useState(params.get("token") ?? "");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await acceptInvite({ token: token.trim(), username: username.trim(), password });
      setDone(true);
    } catch (err) {
      setError(apiMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const input =
    "w-full rounded-md border border-neutral-300 px-3 py-2 text-sm";

  if (done)
    return (
      <Card className="p-6 text-sm">
        <p className="font-medium text-emerald-700">Account created.</p>
        <p className="mt-2 text-neutral-600">
          Sign in with your new username and password, then set up an
          authenticator app when prompted.
        </p>
        <Button className="mt-4" onClick={() => router.push("/login/")}>
          Go to sign-in
        </Button>
      </Card>
    );

  return (
    <Card className="p-6">
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-neutral-600">
            Invite token
          </label>
          <input
            className={input}
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-neutral-600">
            Choose a username
          </label>
          <input
            className={input}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-neutral-600">
            Choose a password (12+ characters)
          </label>
          <input
            className={input}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
          />
        </div>
        {error && <ErrorNote message={error} />}
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? "Creating…" : "Create my account"}
        </Button>
      </form>
    </Card>
  );
}

export default function InvitePage() {
  return (
    <main className="mx-auto max-w-sm px-6 py-16">
      <h1 className="text-xl font-semibold">Join Campus</h1>
      <p className="mt-2 text-sm text-neutral-600">
        You were invited by an administrator. Set your username and password
        below.
      </p>
      <div className="mt-6">
        <Suspense fallback={null}>
          <AcceptForm />
        </Suspense>
      </div>
    </main>
  );
}
