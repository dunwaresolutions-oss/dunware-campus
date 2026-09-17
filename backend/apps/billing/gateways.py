"""
`PaymentGateway` interface (see docs/PII_SECURITY.md — no card data, no PCI
scope: every online gateway here is a hosted-checkout redirect, Campus never
sees a card number).

`ManualGateway` records a cash / cheque / e-transfer / card-terminal payment
an operator already received off-platform — the universal default and the
only option where no online gateway serves the school's country.

`OnlineGateway` is the P2 contract (Campus_Payments_Action_Plan.html
§flow) for a hosted-checkout gateway: `initialize()` starts a checkout and
returns `(checkout_url, gateway_session_id)`, `verify()` asks the gateway
what actually happened for one `PaymentAttempt`. `PaystackGateway` (P3) and,
as of this pass, `FlutterwaveGateway` + a real `StripeGateway` (P5) are all
real implementations — Kanoo stays out (Damien, 2026-09-16: leave it out
until CaribPay responds to the API access request).

Two contract details worth being explicit about, since they came from
actually implementing three different gateways rather than the plan's
original pseudocode alone:
  - `initialize()` returns a 2-tuple, not just a URL. Paystack/Flutterwave
    verify by the same reference *we* generate (`attempt.reference`), but
    Stripe's Checkout Sessions API has no "look up by your own reference"
    endpoint - only by Stripe's own session id. The second tuple element is
    that id where a gateway needs one, else "".
  - `verify()` takes the whole `PaymentAttempt`, not a bare reference
    string - for the same reason: Stripe's verify needs
    `attempt.gateway_session_id`, not `attempt.reference`.

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
    one has no real implementation yet (Kanoo - P5 left it out, per Damien,
    until CaribPay responds)."""


@dataclasses.dataclass
class VerifiedResult:
    """What `OnlineGateway.verify()` reports back — matches
    Campus_Payments_Action_Plan.html's `{status, amount_cents, currency,
    channel, raw}` pseudocode."""

    status: str  # "success" | "failed" | "pending"
    amount_cents: int | None
    currency: str | None
    channel: str
    raw: dict[str, Any]


def _guardian_email(invoices: list[Invoice]) -> str:
    """Every gateway here needs a payer email (Paystack/Flutterwave
    `customer.email`, Stripe `customer_email`) - shared lookup so the
    "which guardian, and what if none has an email on file" logic exists
    exactly once. `invoices` may be several (a combined family payment) -
    the caller (`services.initiate_online_payment`) already enforced that
    every one of them resolves to the same billing guardian, so the first
    invoice's `effective_guardian` is authoritative for all of them."""
    guardian = invoices[0].effective_guardian
    email = getattr(guardian, "email", "") or ""
    if not email:
        raise GatewayError(
            "This invoice's guardian has no email on file - required to start a hosted checkout."
        )
    return email


def _description(invoices: list[Invoice]) -> str:
    """Human-readable line item / product name for a checkout - one invoice
    number, or a combined-payment summary for a family's multi-child
    checkout (Campus_Payments_Action_Plan.html - multi-invoice combine)."""
    if len(invoices) == 1:
        return f"Invoice {invoices[0].invoice_number}"
    numbers = ", ".join(inv.invoice_number for inv in invoices)
    return f"{len(invoices)} invoices ({numbers})"


def _safe_json(resp) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {}


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
    silently doing nothing.

    `config` defaults to `None` so `get_gateway()`'s legacy
    `settings.FEATURE_PAYMENTS_GATEWAY` fallback path (pre-P2, still used
    when no `GatewayConfig` row exists at all) can still construct one
    without a config to type-check against — `charge()`/`refund()` raise
    either way, and a real `initialize()`/`verify()` call raises
    `GatewayNotConfigured` cleanly rather than an `AttributeError` on
    `self.config`."""

    def __init__(self, config: GatewayConfig | None = None):
        self.config = config

    def _require_config(self) -> GatewayConfig:
        if self.config is None:
            raise GatewayNotConfigured(f"{type(self).__name__} has no GatewayConfig set.")
        return self.config

    @abc.abstractmethod
    def initialize(self, *, invoices: list[Invoice], attempt: PaymentAttempt,
                   return_url: str = "") -> tuple[str, str]:
        """Start a hosted checkout for `attempt`, covering one or several
        invoices (a family's combined payment - Campus_Payments_Action_Plan
        multi-invoice combine). `attempt.amount_cents` is already the real
        total to charge (which may be less than the invoices' combined
        balance - a partial payment); `invoices` is only needed here for
        the payer's email and a human-readable description. Returns
        `(checkout_url, gateway_session_id)` - the second element is ""
        for a gateway that verifies by `attempt.reference` directly."""

    @abc.abstractmethod
    def verify(self, attempt: PaymentAttempt) -> VerifiedResult:
        """Ask the gateway what actually happened for `attempt`."""

    def test_connection(self) -> tuple[bool, str]:
        """Ping the gateway's auth endpoint with the configured keys — the
        companion Payments tab's "Test connection" button (P2), and
        `manage payments_test`. No default implementation: Kanoo (left out
        of this pass) has nothing to ping yet."""
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
    Docs: https://paystack.com/docs/api/transaction/. Amounts are the
    currency's smallest subunit (kobo/cents) throughout - matches Campus's
    own `*_cents` convention exactly, no conversion needed."""

    BASE_URL = "https://api.paystack.co"
    TIMEOUT = 15.0

    def _client(self):
        import httpx

        cfg = self._require_config()
        return httpx.Client(
            base_url=self.BASE_URL, timeout=self.TIMEOUT,
            headers={"Authorization": f"Bearer {cfg.secret_key}"},
        )

    def initialize(self, *, invoices: list[Invoice], attempt: PaymentAttempt,
                   return_url: str = "") -> tuple[str, str]:
        import httpx

        email = _guardian_email(invoices)
        payload = {
            "email": email,
            "amount": attempt.amount_cents,
            "currency": attempt.currency,
            "reference": attempt.reference,
            "metadata": {"description": _description(invoices)},
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
        return body["data"]["authorization_url"], ""

    def verify(self, attempt: PaymentAttempt) -> VerifiedResult:
        import httpx

        try:
            with self._client() as client:
                resp = client.get(f"/transaction/verify/{attempt.reference}")
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
            status=status, amount_cents=data.get("amount"), currency=data.get("currency"),
            channel=data.get("channel", ""), raw=body,
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


class FlutterwaveGateway(OnlineGateway):
    """Real (P5): raw REST via `httpx`. Docs:
    https://developer.flutterwave.com/docs/making-payments/standard.

    **Amounts are in the currency's MAJOR unit here (e.g. naira, not kobo)
    - unlike Paystack, which matches Campus's own cents convention
    directly.** Converted at the boundary in both directions so nothing
    above this class ever has to think about it; getting this wrong would
    silently produce a false MISMATCH on every real transaction (100x off),
    so it's called out explicitly rather than left as an implicit detail."""

    BASE_URL = "https://api.flutterwave.com/v3"
    TIMEOUT = 15.0

    def _client(self):
        import httpx

        cfg = self._require_config()
        return httpx.Client(
            base_url=self.BASE_URL, timeout=self.TIMEOUT,
            headers={"Authorization": f"Bearer {cfg.secret_key}"},
        )

    def initialize(self, *, invoices: list[Invoice], attempt: PaymentAttempt,
                   return_url: str = "") -> tuple[str, str]:
        import httpx

        email = _guardian_email(invoices)
        payload = {
            "tx_ref": attempt.reference,
            "amount": attempt.amount_cents / 100,  # major units - see class docstring
            "currency": attempt.currency,
            "redirect_url": return_url,
            "customer": {"email": email},
            "customizations": {"description": _description(invoices)},
        }
        try:
            with self._client() as client:
                resp = client.post("/payments", json=payload)
        except httpx.HTTPError as e:
            raise GatewayError(f"Flutterwave initialize failed: {e}") from e
        body = _safe_json(resp)
        if resp.status_code >= 400 or body.get("status") != "success":
            msg = body.get("message", resp.text)[:300]
            raise GatewayError(f"Flutterwave initialize refused: {msg}")
        return body["data"]["link"], ""

    def verify(self, attempt: PaymentAttempt) -> VerifiedResult:
        import httpx

        try:
            with self._client() as client:
                resp = client.get(
                    "/transactions/verify_by_reference", params={"tx_ref": attempt.reference}
                )
        except httpx.HTTPError as e:
            raise GatewayError(f"Flutterwave verify failed: {e}") from e
        body = _safe_json(resp)
        if resp.status_code >= 400 or body.get("status") != "success":
            msg = body.get("message", resp.text)[:300]
            raise GatewayError(f"Flutterwave verify refused: {msg}")
        data = body.get("data") or {}
        # "successful" | "failed" | "cancelled" | ...
        raw_status = (data.get("status") or "").lower()
        status = "success" if raw_status == "successful" else (
            "failed" if raw_status in ("failed", "cancelled") else "pending"
        )
        amount = data.get("amount")
        amount_cents = round(amount * 100) if amount is not None else None  # major -> cents
        return VerifiedResult(
            status=status, amount_cents=amount_cents,
            currency=data.get("currency"), channel=data.get("payment_type", ""), raw=body,
        )

    def test_connection(self) -> tuple[bool, str]:
        import httpx

        try:
            with self._client() as client:
                resp = client.get("/transactions", params={"page": 1})
        except httpx.HTTPError as e:
            return False, f"could not reach Flutterwave: {e}"
        body = _safe_json(resp)
        if resp.status_code in (401, 403):
            return False, "Flutterwave rejected the secret key (unauthorized)."
        if resp.status_code >= 400:
            return False, f"Flutterwave returned an error: {body.get('message', resp.text)[:200]}"
        return True, "Flutterwave authenticated successfully."


class StripeGateway(OnlineGateway):
    """Real (P5): Stripe Checkout Sessions via raw REST. Docs:
    https://stripe.com/docs/api/checkout/sessions.

    Two things that make Stripe genuinely different from Paystack/
    Flutterwave, not just a different base URL:
      - The API takes `application/x-www-form-urlencoded` (bracket notation
        for nested fields), not JSON.
      - Auth is HTTP Basic with the secret key as the username and an empty
        password - not a Bearer header.
      - There's no "verify by your own reference" endpoint - only by
        Stripe's own session id, which is why `initialize()` returns it as
        the second tuple element and `verify()` needs the whole `attempt`
        (see the module docstring)."""

    BASE_URL = "https://api.stripe.com/v1"
    TIMEOUT = 15.0

    def _client(self):
        import httpx

        cfg = self._require_config()
        return httpx.Client(base_url=self.BASE_URL, timeout=self.TIMEOUT, auth=(cfg.secret_key, ""))

    def initialize(self, *, invoices: list[Invoice], attempt: PaymentAttempt,
                   return_url: str = "") -> tuple[str, str]:
        import httpx

        if not return_url:
            raise GatewayError(
                "Stripe Checkout requires a return_url (success/cancel destination)."
            )
        email = _guardian_email(invoices)
        sep = "&" if "?" in return_url else "?"
        success_url = f"{return_url}{sep}session_id={{CHECKOUT_SESSION_ID}}"
        # One line item for `attempt.amount_cents` as a whole, not one per
        # invoice - the total may be a custom partial amount that doesn't
        # correspond 1:1 to each invoice's own balance (see
        # services.allocate_payment), so per-invoice line amounts would be
        # fiction. The description names every invoice instead.
        form = {
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": return_url,
            "customer_email": email,
            "client_reference_id": attempt.reference,
            "line_items[0][price_data][currency]": attempt.currency.lower(),
            "line_items[0][price_data][unit_amount]": str(attempt.amount_cents),
            "line_items[0][price_data][product_data][name]": _description(invoices),
            "line_items[0][quantity]": "1",
        }
        try:
            with self._client() as client:
                resp = client.post("/checkout/sessions", data=form)
        except httpx.HTTPError as e:
            raise GatewayError(f"Stripe initialize failed: {e}") from e
        body = _safe_json(resp)
        if resp.status_code >= 400:
            msg = (body.get("error") or {}).get("message", resp.text)[:300]
            raise GatewayError(f"Stripe initialize refused: {msg}")
        return body["url"], body["id"]

    def verify(self, attempt: PaymentAttempt) -> VerifiedResult:
        import httpx

        if not attempt.gateway_session_id:
            # initialize() never completed far enough to get a session id -
            # nothing to check yet, not a failure.
            return VerifiedResult(
                status="pending", amount_cents=None, currency=None, channel="", raw={},
            )
        try:
            with self._client() as client:
                resp = client.get(f"/checkout/sessions/{attempt.gateway_session_id}")
        except httpx.HTTPError as e:
            raise GatewayError(f"Stripe verify failed: {e}") from e
        body = _safe_json(resp)
        if resp.status_code >= 400:
            msg = (body.get("error") or {}).get("message", resp.text)[:300]
            raise GatewayError(f"Stripe verify refused: {msg}")
        # "paid" | "unpaid" | "no_payment_required"
        payment_status = (body.get("payment_status") or "").lower()
        # "open" | "complete" | "expired"
        session_status = (body.get("status") or "").lower()
        if payment_status == "paid":
            status = "success"
        elif session_status == "expired":
            status = "failed"
        else:
            status = "pending"
        currency = body.get("currency")
        return VerifiedResult(
            status=status, amount_cents=body.get("amount_total"),
            currency=currency.upper() if currency else None, channel="card", raw=body,
        )

    def test_connection(self) -> tuple[bool, str]:
        import httpx

        try:
            with self._client() as client:
                resp = client.get("/checkout/sessions", params={"limit": 1})
        except httpx.HTTPError as e:
            return False, f"could not reach Stripe: {e}"
        body = _safe_json(resp)
        if resp.status_code == 401:
            return False, "Stripe rejected the secret key (401 unauthorized)."
        if resp.status_code >= 400:
            msg = (body.get("error") or {}).get("message", resp.text)[:200]
            return False, f"Stripe returned an error: {msg}"
        return True, "Stripe authenticated successfully."


# Gateways with a real OnlineGateway implementation. Kanoo stays out per
# Damien (2026-09-16): "leave Kanoo out until we get word from CaribPay,
# then we can add it to the system." GatewayConfig can still be *set* to
# KANOO (the companion's eventual Payments tab, or set_gateway_config, don't
# need to wait on the code) - get_gateway() just falls through to
# ManualGateway below, nothing silently pretends to charge a card.
_ONLINE_IMPLEMENTATIONS = {
    Gateway.PAYSTACK: PaystackGateway,
    Gateway.FLUTTERWAVE: FlutterwaveGateway,
    Gateway.STRIPE: StripeGateway,
}


def online_gateway_class(gateway_code: str) -> type[OnlineGateway] | None:
    """The real `OnlineGateway` subclass for `gateway_code`, if one is built
    yet - `None` for MANUAL or an unbuilt gateway (Kanoo). Used by
    `manage payments_test --gateway ...` to test not-yet-saved values
    (the companion GUI's Test Connection button) without going through
    `get_gateway()`, which only ever looks at the persisted `GatewayConfig`."""
    return _ONLINE_IMPLEMENTATIONS.get(gateway_code)


def get_gateway() -> PaymentGateway:
    cfg = GatewayConfig.objects.first()
    if cfg and cfg.is_online:
        impl = _ONLINE_IMPLEMENTATIONS.get(cfg.gateway)
        if impl is not None:
            return impl(cfg)
        # Kanoo (or any future gateway not yet built): configured but has no
        # real implementation - manual recording still works.
        return ManualGateway()
    name = getattr(settings, "FEATURE_PAYMENTS_GATEWAY", "manual")
    if name == "manual":
        return ManualGateway()
    return StripeGateway()
