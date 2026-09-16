"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { getPaymentAttempt, type PaymentAttempt } from "@/lib/portal";
import { Button, Card, Spinner } from "@/components/ui";
import { money, date } from "@/lib/format";

// Long enough for a real card authorization/3-D-Secure round trip, short
// enough not to leave the tab spinning forever if the gateway never calls
// back - after this we stop polling automatically and let the parent
// check again by hand (see "Check again" below).
const POLL_INTERVAL_MS = 2500;
const MAX_POLLS = 40; // ~100s of polling

const STORAGE_KEY = "campus_pending_payment_ref";

/**
 * Which checkout is this? In priority order:
 *  1. `?reference=` / `?tx_ref=` - Paystack and Flutterwave both redirect
 *     back with OUR OWN reference echoed as a callback query param (we set
 *     it as `reference`/`tx_ref` when starting the checkout), so this works
 *     even if the browser tab/storage didn't survive the round trip.
 *  2. sessionStorage, set right before redirecting to the gateway - the
 *     only signal Stripe's redirect gives us is its own session_id, not our
 *     reference, so this is what makes Stripe's return page work at all.
 */
function resolveReference(params: URLSearchParams): string | null {
  const fromQuery = params.get("reference") || params.get("tx_ref");
  if (fromQuery) return fromQuery;
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function statusCopy(attempt: PaymentAttempt) {
  switch (attempt.status) {
    case "SUCCESS":
      return {
        tone: "success" as const,
        title: "Payment received",
        body: "Thank you — the invoice below has been updated. A receipt is sent by the payment provider.",
      };
    case "FAILED":
    case "ABANDONED":
      return {
        tone: "error" as const,
        title: "Payment did not go through",
        body: "Nothing was charged. You can try again from your billing section.",
      };
    case "MISMATCH":
      return {
        tone: "warning" as const,
        title: "We need to double-check this payment",
        body: "The provider reported something we couldn't automatically match to what was expected. Please contact the front office before trying again — do not pay twice.",
      };
    default:
      return {
        tone: "pending" as const,
        title: "Confirming your payment…",
        body: "This usually takes a few seconds.",
      };
  }
}

function ReturnStatus() {
  const params = useSearchParams();
  const [reference] = useState<string | null>(() => resolveReference(params));
  const [attempt, setAttempt] = useState<PaymentAttempt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gaveUp, setGaveUp] = useState(false);
  const pollsRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function startPolling(ref: string) {
    let cancelled = false;

    async function tick() {
      try {
        const a = await getPaymentAttempt(ref);
        if (cancelled) return;
        setAttempt(a);
        setError(null);
        if (a.status === "PENDING" || a.status === "INITIALIZED") {
          pollsRef.current += 1;
          if (pollsRef.current < MAX_POLLS) {
            timerRef.current = setTimeout(tick, POLL_INTERVAL_MS);
          } else {
            setGaveUp(true);
          }
        } else {
          try {
            sessionStorage.removeItem(STORAGE_KEY);
          } catch {
            // ignore
          }
        }
      } catch {
        if (!cancelled) setError("Couldn't check this payment's status just now.");
      }
    }
    tick();

    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }

  useEffect(() => {
    if (!reference) return;
    return startPolling(reference);
  }, [reference]);

  function checkAgain() {
    if (!reference) return;
    pollsRef.current = 0;
    setGaveUp(false);
    setError(null);
    startPolling(reference);
  }

  if (!reference) {
    return (
      <Card className="p-6 text-sm">
        <p className="font-medium">We couldn&apos;t find that payment</p>
        <p className="mt-2 text-[var(--campus-muted)]">
          If you completed checkout, it may still be processing — check My Billing in a few
          minutes, or contact the front office if a charge appears on your card statement.
        </p>
        <Link href="/portal/">
          <Button className="mt-4">Back to my portal</Button>
        </Link>
      </Card>
    );
  }

  if (error && !attempt) {
    return (
      <Card className="p-6 text-sm">
        <p className="font-medium text-red-600">{error}</p>
        <Button className="mt-4" onClick={checkAgain}>
          Check again
        </Button>
      </Card>
    );
  }

  if (!attempt) {
    return (
      <Card className="p-6">
        <Spinner />
      </Card>
    );
  }

  const copy = statusCopy(attempt);
  const toneCls = {
    success: "text-emerald-700 dark:text-emerald-400",
    error: "text-red-600 dark:text-red-400",
    warning: "text-amber-700 dark:text-amber-400",
    pending: "text-[var(--campus-fg)]",
  }[copy.tone];

  return (
    <Card className="p-6 text-sm">
      <p className={`text-base font-semibold ${toneCls}`}>{copy.title}</p>
      <p className="mt-2 text-[var(--campus-muted)]">{copy.body}</p>

      {attempt.allocations.length > 0 && (
        <ul className="mt-4 space-y-1.5 border-t border-[var(--campus-line)] pt-4">
          {attempt.allocations.map((a) => (
            <li key={a.invoice} className="flex items-center justify-between">
              <span>
                {a.student_name}
                <span className="text-xs text-[var(--campus-muted)]"> · {a.invoice_number}</span>
              </span>
              <span className="font-medium">{money(a.allocated_cents, attempt.currency)}</span>
            </li>
          ))}
          <li className="flex items-center justify-between border-t border-[var(--campus-line)] pt-1.5 font-semibold">
            <span>Total</span>
            <span>{money(attempt.amount_cents, attempt.currency)}</span>
          </li>
        </ul>
      )}

      <p className="mt-4 text-xs text-[var(--campus-muted)]">
        {date(attempt.updated_at)} · reference {attempt.reference}
      </p>

      {(attempt.status === "PENDING" || attempt.status === "INITIALIZED") && (
        <div className="mt-4">
          {gaveUp ? (
            <>
              <p className="mb-2 text-xs text-[var(--campus-muted)]">
                Still waiting to hear back from the payment provider.
              </p>
              <Button onClick={checkAgain}>Check again</Button>
            </>
          ) : (
            <Spinner />
          )}
        </div>
      )}

      <Link href="/portal/">
        <Button className="mt-4" variant={attempt.status === "SUCCESS" ? "primary" : "ghost"}>
          Back to my portal
        </Button>
      </Link>
    </Card>
  );
}

export default function PayReturnPage() {
  return (
    <main className="mx-auto max-w-lg px-5 py-12 sm:px-8">
      <h1 className="mb-6 text-xl font-semibold text-[var(--campus-fg)]">Payment status</h1>
      <Suspense fallback={<Card className="p-6"><Spinner /></Card>}>
        <ReturnStatus />
      </Suspense>
    </main>
  );
}
