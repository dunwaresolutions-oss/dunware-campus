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
from .models import Invoice, Payment, PaymentAttempt

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


def initiate_online_payment(
    invoice: Invoice, *, initialized_by=None, return_url: str = ""
) -> PaymentAttempt:
    """Start a hosted checkout for `invoice`'s current balance (P3 §flow,
    step 2). Raises `GatewayNotConfigured` if this install has no real
    online gateway wired up (still MANUAL, or an unimplemented one - see
    `gateways._ONLINE_IMPLEMENTATIONS`)."""
    if invoice.status == Invoice.Status.VOID:
        raise ValueError("Cannot start a checkout for a void invoice.")
    gateway = get_gateway()
    if not isinstance(gateway, OnlineGateway):
        raise GatewayNotConfigured(
            "No online payment gateway is configured for this install - use the "
            "manual mark-paid workflow, or configure one with "
            "`manage set_gateway_config`."
        )
    amount_cents = invoice.balance_cents
    if amount_cents <= 0:
        raise ValueError("This invoice has no outstanding balance to pay.")

    attempt = PaymentAttempt.objects.create(
        invoice=invoice, gateway=gateway.config.gateway, reference=_generate_reference(invoice),
        amount_cents=amount_cents, currency=invoice.currency,
        status=PaymentAttempt.Status.INITIALIZED,
        initialized_by=initialized_by if getattr(initialized_by, "pk", None) else None,
    )
    try:
        checkout_url, gateway_session_id = gateway.initialize(
            invoice=invoice, attempt=attempt, return_url=return_url
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
           summary=f"online checkout started ({attempt.gateway}, ${amount_cents / 100:.2f})",
           actor=initialized_by)
    return attempt


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
            payment = Payment.objects.create(
                invoice=attempt.invoice, amount_cents=attempt.amount_cents,
                source=Payment.Source.GATEWAY, gateway=attempt.gateway,
                gateway_reference=attempt.reference, received_at=timezone.now(),
                note=f"via {attempt.gateway.title()}",
            )
            attempt.invoice.refresh_status()
            summary = f"payment recorded (${attempt.amount_cents / 100:.2f}, {attempt.gateway})"
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
