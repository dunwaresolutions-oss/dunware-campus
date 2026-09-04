"""
`PaymentGateway` interface (see docs/PII_SECURITY.md — no card data, no PCI
scope in v1).

`ManualGateway` is the only gateway wired up: it records a cash / cheque /
e-transfer payment an operator already received off-platform. `StripeGateway`
is a **stub** — its shape documents the v2 contract but every method raises
`NotImplementedError` until real card processing is built (`# TODO v2`).
`settings.FEATURE_PAYMENTS_GATEWAY` selects which one `get_gateway()` returns;
only `"manual"` is a real option today.
"""
from __future__ import annotations

import abc

from django.conf import settings
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record

from .models import Invoice, Payment


class PaymentGateway(abc.ABC):
    @abc.abstractmethod
    def charge(self, invoice: Invoice, amount_cents: int, **kwargs) -> Payment:
        """Record (or process) a payment against an invoice."""

    @abc.abstractmethod
    def refund(self, payment: Payment, amount_cents: int, **kwargs) -> None:
        """Reverse all or part of a payment."""


class ManualGateway(PaymentGateway):
    """The only real gateway in v1: cash / cheque / e-transfer, entered by
    staff after the money has already changed hands off-platform."""

    def charge(self, invoice: Invoice, amount_cents: int, *, method, reference="",
              received_by=None, note="") -> Payment:
        payment = Payment.objects.create(
            invoice=invoice, amount_cents=amount_cents, method=method,
            reference=reference[:100], received_at=timezone.now(),
            received_by=received_by if getattr(received_by, "pk", None) else None,
            note=note[:255],
        )
        invoice.refresh_status()
        record(AuditAction.CREATE, payment,
               summary=f"payment recorded (${amount_cents / 100:.2f}, {method})",
               actor=received_by)
        return payment

    def refund(self, payment: Payment, amount_cents: int, **kwargs) -> None:
        # No automated reversal in v1 — issue a Credit and record it manually.
        raise NotImplementedError(
            "ManualGateway does not reverse a payment automatically; "
            "record a Credit against the student instead."
        )


class StripeGateway(PaymentGateway):
    """PLACEHOLDER — v2. Not wired to any credentials; both methods refuse to
    run so a misconfiguration can never silently attempt a real charge."""

    def charge(self, invoice: Invoice, amount_cents: int, **kwargs) -> Payment:  # TODO v2
        raise NotImplementedError(
            "StripeGateway is a placeholder for v2 — card processing is not built."
        )

    def refund(self, payment: Payment, amount_cents: int, **kwargs) -> None:  # TODO v2
        raise NotImplementedError(
            "StripeGateway is a placeholder for v2 — card processing is not built."
        )


def get_gateway() -> PaymentGateway:
    name = getattr(settings, "FEATURE_PAYMENTS_GATEWAY", "manual")
    if name == "manual":
        return ManualGateway()
    return StripeGateway()
