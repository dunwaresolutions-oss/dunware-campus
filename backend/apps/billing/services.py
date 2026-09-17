"""Invoice lifecycle: draft -> issued -> (partially) paid / void."""
from __future__ import annotations

import json
import logging
import secrets

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record

from .gateways import GatewayError, GatewayNotConfigured, OnlineGateway, get_gateway
from .models import Invoice, Payment, PaymentAttempt, PaymentAttemptInvoice

logger = logging.getLogger(__name__)

# A poll faster than this just re-serves the attempt's current cached status
# instead of hitting the gateway's API again - the portal's return-poll page
# is expected to poll every couple of seconds for up to ~3 min
# (Campus_Payments_Action_Plan.html §flow); re-verifying on every single one
# of those requests would be needlessly chatty against a real gateway.
_VERIFY_MIN_INTERVAL_SECONDS = 5


def issue_invoice(invoice: Invoice, *, actor=None) -> Invoice:
    if invoice.status != Invoice.Status.DRAFT:
        return invoice
    invoice.status = Invoice.Status.ISSUED
    invoice.issued_at = timezone.now()
    invoice.save(update_fields=["status", "issued_at", "updated_at"])
    record(AuditAction.UPDATE, invoice, summary="invoice issued", actor=actor)
    return invoice


@transaction.atomic
def mark_paid(invoice: Invoice, *, amount_cents: int, method: str, reference: str = "",
             by=None, note: str = "") -> Payment:
    if invoice.status == Invoice.Status.VOID:
        raise ValueError("Cannot record a payment against a void invoice.")
    gateway = get_gateway()
    return gateway.charge(
        invoice, amount_cents, method=method, reference=reference, received_by=by, note=note
    )


def void_invoice(invoice: Invoice, *, reason: str = "", actor=None) -> Invoice:
    invoice.status = Invoice.Status.VOID
    invoice.notes = (invoice.notes + f" [voided: {reason}]").strip()[:255]
    invoice.save(update_fields=["status", "notes", "updated_at"])
    record(AuditAction.UPDATE, invoice, summary=f"invoice voided ({reason or 'no reason given'})",
           actor=actor)
    return invoice


@transaction.atomic
def initiate_online_payment(
    invoices: list[Invoice], *, initialized_by=None, return_url: str = "",
    amount_cents: int | None = None,
) -> PaymentAttempt:
    """Start a hosted checkout covering one or several invoices at once - a
    family paying for two or more children in a single real gateway charge
    (Campus_Payments_Action_Plan.html multi-invoice combine), not one
    transaction fee per child. `invoices` must all be billed to the same
    guardian (`Invoice.guardian`) - that FK is the only thing that decides
    what may be combined, deliberately not address or "any linked guardian",
    so a step-child's or estranged co-parent's invoice can never end up on
    someone else's combined charge (see `Invoice.is_visible_to`). Role-based
    "is this guardian allowed to pay *this* invoice at all" is the caller's
    job (`views.InvoiceViewSet.pay`); this function only enforces that a
    combine is internally consistent.

    `amount_cents` lets the payer enter a custom total smaller than the
    invoices' full combined balance (partial payment is allowed - decision
    confirmed 2026-09-16) - defaults to the full combined balance. Whatever
    the total ends up being, `allocate_payment` splits it back across each
    invoice's own ledger proportionally, so every invoice's balance still
    updates correctly even though only one real charge happened.

    Raises `GatewayNotConfigured` if this install has no real online gateway
    wired up (still MANUAL, or an unimplemented one - see
    `gateways._ONLINE_IMPLEMENTATIONS`)."""
    if not invoices:
        raise ValueError("At least one invoice is required.")
    if any(inv.status == Invoice.Status.VOID for inv in invoices):
        raise ValueError("Cannot start a checkout for a void invoice.")
    # `effective_guardian`, not the raw `guardian_id` column - an invoice
    # created before `Invoice.save()` started defaulting it (2026-09-16)
    # still has it NULL until backfilled, and would otherwise make even a
    # single, uncombined invoice unpayable.
    guardian_ids = {
        (g.id if (g := inv.effective_guardian) else None) for inv in invoices
    }
    if len(guardian_ids) > 1 or None in guardian_ids:
        raise ValueError(
            "All invoices in a combined payment must be billed to the same guardian."
        )
    currencies = {inv.currency for inv in invoices}
    if len(currencies) > 1:
        raise ValueError("Cannot combine invoices billed in different currencies.")

    gateway = get_gateway()
    if not isinstance(gateway, OnlineGateway):
        raise GatewayNotConfigured(
            "No online payment gateway is configured for this install - use the "
            "manual mark-paid workflow, or configure one with "
            "`manage set_gateway_config`."
        )

    combined_balance = sum(inv.balance_cents for inv in invoices)
    if combined_balance <= 0:
        raise ValueError("These invoices have no outstanding balance to pay.")
    if amount_cents is None:
        amount_cents = combined_balance
    elif amount_cents <= 0:
        raise ValueError("The payment amount must be greater than zero.")
    elif amount_cents > combined_balance:
        raise ValueError("The payment amount cannot exceed the combined outstanding balance.")

    allocations = allocate_payment(invoices, amount_cents)

    attempt = PaymentAttempt.objects.create(
        gateway=gateway.config.gateway, reference=_generate_reference(invoices[0]),
        amount_cents=amount_cents, currency=invoices[0].currency,
        status=PaymentAttempt.Status.INITIALIZED,
        initialized_by=initialized_by if getattr(initialized_by, "pk", None) else None,
    )
    PaymentAttemptInvoice.objects.bulk_create([
        PaymentAttemptInvoice(attempt=attempt, invoice=inv, allocated_cents=cents)
        for inv, cents in allocations
    ])
    try:
        checkout_url, gateway_session_id = gateway.initialize(
            invoices=invoices, attempt=attempt, return_url=return_url
        )
    except GatewayError:
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.save(update_fields=["status", "updated_at"])
        raise
    attempt.checkout_url = checkout_url
    attempt.gateway_session_id = gateway_session_id
    attempt.status = PaymentAttempt.Status.PENDING
    attempt.save(update_fields=["checkout_url", "gateway_session_id", "status", "updated_at"])
    record(AuditAction.CREATE, attempt,
           summary=f"online checkout started ({attempt.gateway}, ${amount_cents / 100:.2f}, "
                   f"{len(invoices)} invoice{'s' if len(invoices) != 1 else ''})",
           actor=initialized_by)
    return attempt


def allocate_payment(invoices: list[Invoice], total_cents: int) -> list[tuple[Invoice, int]]:
    """Split `total_cents` (the real amount the gateway will actually
    charge, possibly less than the invoices' combined balance - a partial
    payment) across `invoices`, proportional to each invoice's own
    `balance_cents`. Largest-remainder method - same technique already used
    for `seed_demo`'s grade-size apportionment - so the per-invoice cents
    always sum to exactly `total_cents` (a naive proportional round can be
    off by a cent or two, which billing math can't tolerate)."""
    weights = [inv.balance_cents for inv in invoices]
    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError("Nothing outstanding to allocate.")
    shares: list[list] = []
    remainders: list[float] = []
    allocated_so_far = 0
    for inv, weight in zip(invoices, weights, strict=True):
        exact = total_cents * weight / total_weight
        base = int(exact)
        shares.append([inv, base])
        remainders.append(exact - base)
        allocated_so_far += base
    leftover = total_cents - allocated_so_far
    for i in sorted(range(len(invoices)), key=lambda i: remainders[i], reverse=True)[:leftover]:
        shares[i][1] += 1
    return [(inv, cents) for inv, cents in shares]


def _generate_reference(invoice: Invoice) -> str:
    # Human-traceable back to the invoice, but not guessable/enumerable -
    # matches every gateway's own "must be unique" requirement.
    return f"campus_{invoice.invoice_number or invoice.pk}_{secrets.token_hex(6)}"


@transaction.atomic
def resolve_payment_attempt(attempt: PaymentAttempt) -> PaymentAttempt:
    """Ask the gateway what actually happened for `attempt` and apply the
    result. This is the confirmation path P3 needs to be end-to-end usable
    on its own, ahead of P4's scheduled poller: called live from the
    payment-attempts detail endpoint the portal's return-poll page hits, and
    (once P4 exists) from the same poller job on a schedule - same function
    either way, so there is only one place this logic lives.

    A terminal attempt (SUCCESS/FAILED/ABANDONED/MISMATCH) is never
    re-verified - it's already resolved."""
    if attempt.status in (
        PaymentAttempt.Status.SUCCESS, PaymentAttempt.Status.FAILED,
        PaymentAttempt.Status.ABANDONED, PaymentAttempt.Status.MISMATCH,
    ):
        return attempt
    if attempt.last_checked_at:
        idle_seconds = (timezone.now() - attempt.last_checked_at).total_seconds()
        if idle_seconds < _VERIFY_MIN_INTERVAL_SECONDS:
            return attempt

    gateway = get_gateway()
    if (
        not isinstance(gateway, OnlineGateway)
        or gateway.config is None
        or gateway.config.gateway != attempt.gateway
    ):
        # No configured online gateway, or the install's configured gateway
        # changed since this attempt was created - can't re-verify against a
        # different gateway's API. Leave it exactly as it is rather than guess.
        return attempt

    try:
        result = gateway.verify(attempt)
    except GatewayError as e:
        logger.warning("payment attempt %s: verify failed: %s", attempt.reference, e)
        attempt.last_checked_at = timezone.now()
        attempt.save(update_fields=["last_checked_at", "updated_at"])
        return attempt

    attempt.raw_response = json.dumps(result.raw)[:20_000]
    attempt.channel = result.channel[:30]
    attempt.last_checked_at = timezone.now()

    if result.status == "success":
        amount_ok = result.amount_cents is None or result.amount_cents == attempt.amount_cents
        currency_ok = result.currency is None or result.currency.upper() == attempt.currency.upper()
        if amount_ok and currency_ok:
            allocations = list(attempt.allocations.select_related("invoice"))
            multi = len(allocations) > 1
            note = f"via {attempt.gateway.title()}"
            if multi:
                note += f" (combined payment, {len(allocations)} invoices)"
            for alloc in allocations:
                payment = Payment.objects.create(
                    invoice=alloc.invoice, amount_cents=alloc.allocated_cents,
                    source=Payment.Source.GATEWAY, gateway=attempt.gateway,
                    gateway_reference=attempt.reference, received_at=timezone.now(),
                    note=note,
                )
                alloc.invoice.refresh_status()
                summary = (
                    f"payment recorded (${alloc.allocated_cents / 100:.2f}, {attempt.gateway})"
                )
                record(AuditAction.CREATE, payment, summary=summary)
            attempt.status = PaymentAttempt.Status.SUCCESS
        else:
            logger.warning(
                "payment attempt %s: gateway reports success but amount/currency "
                "mismatch (expected %s %s, got %s %s) - NOT applied",
                attempt.reference, attempt.amount_cents, attempt.currency,
                result.amount_cents, result.currency,
            )
            attempt.status = PaymentAttempt.Status.MISMATCH
    elif result.status == "failed":
        attempt.status = PaymentAttempt.Status.FAILED
    # else "pending" - leave attempt.status as PENDING, try again next poll.

    attempt.save(update_fields=[
        "raw_response", "channel", "last_checked_at", "status", "updated_at",
    ])
    return attempt


def portal_summary(student) -> list[dict]:
    """Read-only shape for the parent portal dashboard — no card data, ever."""
    rows = []
    for inv in Invoice.objects.filter(student=student).exclude(status=Invoice.Status.DRAFT):
        rows.append({
            "id": str(inv.pk),
            "status": inv.status,
            "total_cents": inv.total_cents,
            "balance_cents": inv.balance_cents,
            "due_date": inv.due_date,
        })
    return rows
