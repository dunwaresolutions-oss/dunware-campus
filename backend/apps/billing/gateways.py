"""
`PaymentGateway` interface (see docs/PII_SECURITY.md — no card data, no PCI
scope: every online gateway here is a hosted-checkout redirect, Campus never
sees a card number).

`ManualGateway` records a cash / cheque / e-transfer / card-terminal payment
an operator already received off-platform — the universal default and the
only option where no online gateway serves the school's country.

`OnlineGateway` is the P2 contract (Campus_Payments_Action_Plan.html
§flow) for a hosted-checkout gateway: `initialize()` starts a checkout and
returns a redirect URL, `verify()` asks the gateway (by reference) what
actually happened. `PaystackGateway` (P3) is the first real implementation,
proven against Paystack's own sandbox. `StripeGateway` stays a **stub** —
its real build is P5, out of scope for this pass — every method still
raises `NotImplementedError` so a misconfiguration can never silently
attempt a real charge.

`get_gateway()` first checks this install's `GatewayConfig` (P2's DB-driven
config, set by `manage set_gateway_config`); if none is configured it falls
back to `settings.FEATURE_PAYMENTS_GATEWAY`, same as before P2 — so the
original config-free deployments and tests are unaffected.
"""
from __future__ import annotations

import abc
import dataclasses
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record

from .models import Gateway, GatewayConfig, Invoice, Payment, PaymentAttempt


class GatewayError(Exception):
    """A real call to a gateway's API failed (network, auth, a 4xx/5xx) —
    distinct from a transaction that the gateway itself resolved as failed."""


class GatewayNotConfigured(Exception):
    """No online gateway is configured for this install, or the configured
    one has no real implementation yet (e.g. Flutterwave/Kanoo before P5)."""


@dataclasses.dataclass
class VerifiedResult:
    """What `OnlineGateway.verify()` reports back — matches
    Campus_Payments_Action_Plan.html's `{status, amount_cents, currency,
    channel, raw}` pseudocode exactly."""

    status: str  # "success" | "failed" | "pending"
    amount_cents: int | None
    currency: str | None
    channel: str
    raw: dict[str, Any]


class PaymentGateway(abc.ABC):
    @abc.abstractmethod
    def charge(self, invoice: Invoice, amount_cents: int, **kwargs) -> Payment:
        """Record (or process) a payment against an invoice."""

    @abc.abstractmethod
    def refund(self, payment: Payment, amount_cents: int, **kwargs) -> None:
        """Reverse all or part of a payment."""


class ManualGateway(PaymentGateway):
    """Cash / cheque / e-transfer / card-terminal, entered by staff after the
    money has already changed hands off-platform. The only gateway that ever
    creates a `source=MANUAL` `Payment` directly from `charge()` — online
    gateways go through `PaymentAttempt` + `services.resolve_payment_attempt`
    instead (see `services.py`), since a hosted checkout isn't synchronous."""

    def charge(self, invoice: Invoice, amount_cents: int, *, method, reference="",
              received_by=None, note="") -> Payment:
        payment = Payment.objects.create(
            invoice=invoice, amount_cents=amount_cents, source=Payment.Source.MANUAL,
            method=method, reference=reference[:100], received_at=timezone.now(),
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


class OnlineGateway(PaymentGateway):
    """A hosted-checkout gateway. `charge()`/`refund()` (the synchronous
    manual-recording shape) don't apply here — an online payment is always
    initialize-then-verify, worked through `services.initiate_online_payment`
    / `resolve_payment_attempt`, so both raise pointing there rather than
    silently doing nothing."""

    def __init__(self, config: GatewayConfig):
        self.config = config

    @abc.abstractmethod
    def initialize(self, *, invoice: Invoice, attempt: PaymentAttempt,
                   return_url: str = "") -> str:
        """Start a hosted checkout for `attempt`. Returns the checkout URL."""

    @abc.abstractmethod
    def verify(self, reference: str) -> VerifiedResult:
        """Ask the gateway what actually happened for `reference`."""

    def test_connection(self) -> tuple[bool, str]:
        """Ping the gateway's auth endpoint with the configured keys — the
        companion Payments tab's "Test connection" button (P2), and
        `manage payments_test`. No default implementation: a gateway with no
        real build yet (Flutterwave/Kanoo before P5) has nothing to ping."""
        raise NotImplementedError(f"{type(self).__name__} has no connection test yet.")

    def charge(self, invoice: Invoice, amount_cents: int, **kwargs) -> Payment:
        raise NotImplementedError(
            f"{type(self).__name__} is a hosted-checkout gateway - use "
            "services.initiate_online_payment() + resolve_payment_attempt(), "
            "not charge()."
        )

    def refund(self, payment: Payment, amount_cents: int, **kwargs) -> None:
        raise NotImplementedError(
            f"{type(self).__name__} has no automated refund in v1 - issue a "
            "Credit and refund manually through the gateway's own dashboard."
        )


class PaystackGateway(OnlineGateway):
    """Real (P3): raw REST via `httpx`, proven against Paystack's sandbox.
    Docs: https://paystack.com/docs/api/transaction/."""

    BASE_URL = "https://api.paystack.co"
    TIMEOUT = 15.0

    def _client(self):
        import httpx

        return httpx.Client(
            base_url=self.BASE_URL, timeout=self.TIMEOUT,
            headers={"Authorization": f"Bearer {self.config.secret_key}"},
        )

    def initialize(self, *, invoice: Invoice, attempt: PaymentAttempt,
                   return_url: str = "") -> str:
        import httpx

        guardian = invoice.guardian
        if guardian is None:
            from apps.people.models import GuardianLink

            link = (
                GuardianLink.objects.filter(student=invoice.student, is_primary_contact=True)
                .select_related("guardian").first()
            )
            guardian = link.guardian if link else None
        email = getattr(guardian, "email", "") or ""
        if not email:
            raise GatewayError(
                "Paystack requires a payer email and this invoice's guardian has none on file."
            )
        payload = {
            "email": email,
            "amount": attempt.amount_cents,
            "currency": attempt.currency,
            "reference": attempt.reference,
        }
        if return_url:
            payload["callback_url"] = return_url
        try:
            with self._client() as client:
                resp = client.post("/transaction/initialize", json=payload)
        except httpx.HTTPError as e:
            raise GatewayError(f"Paystack initialize failed: {e}") from e
        body = _safe_json(resp)
        if resp.status_code >= 400 or not body.get("status"):
            msg = body.get("message", resp.text)[:300]
            raise GatewayError(f"Paystack initialize refused: {msg}")
        return body["data"]["authorization_url"]

    def verify(self, reference: str) -> VerifiedResult:
        import httpx

        try:
            with self._client() as client:
                resp = client.get(f"/transaction/verify/{reference}")
        except httpx.HTTPError as e:
            raise GatewayError(f"Paystack verify failed: {e}") from e
        body = _safe_json(resp)
        if resp.status_code >= 400 or not body.get("status"):
            raise GatewayError(f"Paystack verify refused: {body.get('message', resp.text)[:300]}")
        data = body.get("data") or {}
        raw_status = (data.get("status") or "").lower()  # "success" | "failed" | "abandoned" | ...
        status = "success" if raw_status == "success" else (
            "failed" if raw_status in ("failed", "abandoned", "reversed") else "pending"
        )
        return VerifiedResult(
            status=status,
            amount_cents=data.get("amount"),
            currency=data.get("currency"),
            channel=data.get("channel", ""),
            raw=body,
        )


    def test_connection(self) -> tuple[bool, str]:
        import httpx

        try:
            with self._client() as client:
                resp = client.get("/transaction", params={"perPage": 1})
        except httpx.HTTPError as e:
            return False, f"could not reach Paystack: {e}"
        body = _safe_json(resp)
        if resp.status_code == 401:
            return False, "Paystack rejected the secret key (401 unauthorized)."
        if resp.status_code >= 400 or not body.get("status"):
            return False, f"Paystack returned an error: {body.get('message', resp.text)[:200]}"
        return True, "Paystack authenticated successfully."


def _safe_json(resp) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {}


class StripeGateway(PaymentGateway):
    """PLACEHOLDER — real build is P5 (Campus_Payments_Action_Plan.html
    phased plan), out of scope for this P2/P3 pass. Not wired to any
    credentials; both methods refuse to run so a misconfiguration can never
    silently attempt a real charge."""

    def charge(self, invoice: Invoice, amount_cents: int, **kwargs) -> Payment:  # TODO P5
        raise NotImplementedError(
            "StripeGateway is a placeholder for P5 — card processing is not built."
        )

    def refund(self, payment: Payment, amount_cents: int, **kwargs) -> None:  # TODO P5
        raise NotImplementedError(
            "StripeGateway is a placeholder for P5 — card processing is not built."
        )


# Gateways with a real OnlineGateway implementation as of this pass. Flutterwave
# and Kanoo stay MANUAL-equivalent (get_gateway() falls through to ManualGateway
# below) until P5 actually builds them - GatewayConfig can still be *set* to
# either now (the companion's eventual Payments tab, or set_gateway_config,
# don't need to wait on the code), it just won't do anything online yet.
_ONLINE_IMPLEMENTATIONS = {
    Gateway.PAYSTACK: PaystackGateway,
}


def get_gateway() -> PaymentGateway:
    cfg = GatewayConfig.objects.first()
    if cfg and cfg.is_online:
        impl = _ONLINE_IMPLEMENTATIONS.get(cfg.gateway)
        if impl is not None:
            return impl(cfg)
        if cfg.gateway == Gateway.STRIPE:
            return StripeGateway()
        # Flutterwave / Kanoo: configured but not yet built (P5) - manual
        # recording still works, nothing silently pretends to charge a card.
        return ManualGateway()
    name = getattr(settings, "FEATURE_PAYMENTS_GATEWAY", "manual")
    if name == "manual":
        return ManualGateway()
    return StripeGateway()
