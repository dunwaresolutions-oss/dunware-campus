from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.billing.gateways import (
    FlutterwaveGateway,
    GatewayError,
    GatewayNotConfigured,
    ManualGateway,
    PaystackGateway,
    StripeGateway,
    VerifiedResult,
    get_gateway,
)
from apps.billing.models import (
    Credit,
    FeeSchedule,
    Gateway,
    GatewayConfig,
    Invoice,
    InvoiceLine,
    Payment,
    PaymentAttempt,
    PaymentAttemptInvoice,
)
from apps.billing.services import (
    allocate_payment,
    initiate_online_payment,
    issue_invoice,
    mark_paid,
    portal_summary,
    resolve_payment_attempt,
    void_invoice,
)
from apps.people.models import GuardianLink
from apps.people.tests.factories import link_guardian, make_student

pytestmark = pytest.mark.django_db


# ---- P2/P3: online gateway abstraction + Paystack -------------------------

class _FakeResponse:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data
        self.text = str(data)

    def json(self):
        return self._data


class _FakeHttpxClient:
    """Stands in for `httpx.Client` inside `PaystackGateway._client()` -
    real network calls have no place in a test suite. `responses` maps
    "post"/"get" to a single `_FakeResponse` (tests here only ever need one
    call per gateway method)."""

    def __init__(self, **responses):
        self._responses = responses

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, path, json=None, data=None):
        return self._responses["post"]

    def get(self, path, params=None):
        return self._responses["get"]


def _configure_gateway(gateway, secret="sk_test_abc", public="pk_test_abc"):
    cfg = GatewayConfig.load()
    cfg.gateway = gateway
    cfg.mode = GatewayConfig.Mode.TEST
    cfg.secret_key = secret
    cfg.public_key = public
    cfg.save()
    return cfg


def _configure_paystack(secret="sk_test_abc", public="pk_test_abc"):
    return _configure_gateway(Gateway.PAYSTACK, secret, public)


def _paid_invoice_setup(total_cents=5_000):
    kid = make_student()
    link_guardian(kid, email="parent@example.test", is_primary_contact=True)
    inv = Invoice.objects.create(student=kid)
    InvoiceLine.objects.create(invoice=inv, description="Term fee", unit_amount_cents=total_cents)
    issue_invoice(inv)
    return inv


def _attempt_with_allocation(invoice, *, gateway, reference, amount_cents=None, **extra):
    """A saved `PaymentAttempt` with the one `PaymentAttemptInvoice` row every
    real attempt has (single-invoice here: 100% of the amount) - matches
    what `services.initiate_online_payment` itself does, so tests that
    build an attempt directly (bypassing that function) still produce a
    realistic row for `resolve_payment_attempt`/`is_visible_to` to read."""
    amount = invoice.balance_cents if amount_cents is None else amount_cents
    attempt = PaymentAttempt.objects.create(
        gateway=gateway, reference=reference, amount_cents=amount,
        currency=invoice.currency, **extra,
    )
    PaymentAttemptInvoice.objects.create(attempt=attempt, invoice=invoice, allocated_cents=amount)
    return attempt


def test_gateway_config_is_a_singleton():
    a = GatewayConfig.load()
    b = GatewayConfig.load()
    assert a.pk == b.pk
    assert GatewayConfig.objects.count() == 1


def test_get_gateway_returns_paystack_when_configured():
    _configure_paystack()
    gw = get_gateway()
    assert isinstance(gw, PaystackGateway)


def test_get_gateway_falls_back_to_settings_when_unconfigured(settings):
    settings.FEATURE_PAYMENTS_GATEWAY = "manual"
    assert isinstance(get_gateway(), ManualGateway)


def test_paystack_initialize_success(monkeypatch):
    cfg = _configure_paystack()
    inv = _paid_invoice_setup()
    gw = PaystackGateway(cfg)
    fake = _FakeHttpxClient(post=_FakeResponse(200, {
        "status": True, "data": {"authorization_url": "https://checkout.paystack.com/xyz",
                                  "access_code": "abc", "reference": "campus_x"},
    }))
    monkeypatch.setattr(gw, "_client", lambda: fake)
    attempt = _attempt_with_allocation(inv, gateway=Gateway.PAYSTACK, reference="campus_x")
    url, session_id = gw.initialize(invoices=[inv], attempt=attempt)
    assert url == "https://checkout.paystack.com/xyz"
    assert session_id == ""  # Paystack verifies by our own reference - no gateway id needed


def test_paystack_initialize_without_guardian_email_raises():
    cfg = _configure_paystack()
    kid = make_student()  # no guardian linked at all
    inv = Invoice.objects.create(student=kid)
    InvoiceLine.objects.create(invoice=inv, description="fee", unit_amount_cents=1000)
    issue_invoice(inv)
    gw = PaystackGateway(cfg)
    attempt = _attempt_with_allocation(inv, gateway=Gateway.PAYSTACK, reference="campus_y")
    with pytest.raises(GatewayError):
        gw.initialize(invoices=[inv], attempt=attempt)


def test_paystack_initialize_rejects_a_paystack_error(monkeypatch):
    cfg = _configure_paystack()
    inv = _paid_invoice_setup()
    gw = PaystackGateway(cfg)
    fake = _FakeHttpxClient(post=_FakeResponse(401, {"status": False, "message": "Invalid key"}))
    monkeypatch.setattr(gw, "_client", lambda: fake)
    attempt = _attempt_with_allocation(inv, gateway=Gateway.PAYSTACK, reference="campus_z")
    with pytest.raises(GatewayError):
        gw.initialize(invoices=[inv], attempt=attempt)


def _bare_attempt(gateway, reference="some-reference", **extra) -> PaymentAttempt:
    """A `PaymentAttempt` not saved to the DB - `verify()` only reads
    attributes off it (reference / gateway_session_id), doesn't need a real
    row for these gateway-level unit tests."""
    return PaymentAttempt(
        gateway=gateway, reference=reference, amount_cents=1, currency="USD", **extra
    )


def test_paystack_verify_success():
    cfg = _configure_paystack()
    gw = PaystackGateway(cfg)
    result = _mock_verify(gw, _bare_attempt(Gateway.PAYSTACK), status=200, data={
        "status": "success", "amount": 5000, "currency": "ZAR", "channel": "card",
    })
    assert result.status == "success"
    assert result.amount_cents == 5000


def test_paystack_verify_pending():
    cfg = _configure_paystack()
    gw = PaystackGateway(cfg)
    result = _mock_verify(
        gw, _bare_attempt(Gateway.PAYSTACK), status=200, data={"status": "pay_offline"}
    )
    assert result.status == "pending"


def test_paystack_verify_failed():
    cfg = _configure_paystack()
    gw = PaystackGateway(cfg)
    result = _mock_verify(
        gw, _bare_attempt(Gateway.PAYSTACK), status=200, data={"status": "abandoned"}
    )
    assert result.status == "failed"


def _mock_verify(
    gw, attempt, *, status, data, envelope_status=True, get_or_post="get"
) -> VerifiedResult:
    """`envelope_status` is the gateway's own top-level "did this call
    succeed" field - Paystack's is a bool (`True`), Flutterwave's is the
    string `"success"`. A real difference between the two APIs, not
    something to paper over with one hardcoded shape."""
    mp = pytest.MonkeyPatch()
    try:
        body = {"status": envelope_status, "data": data}
        fake = _FakeHttpxClient(**{get_or_post: _FakeResponse(status, body)})
        mp.setattr(gw, "_client", lambda: fake)
        return gw.verify(attempt)
    finally:
        mp.undo()


# ---- P5: Flutterwave + real Stripe -----------------------------------------

def test_get_gateway_returns_flutterwave_when_configured():
    _configure_gateway(Gateway.FLUTTERWAVE)
    assert isinstance(get_gateway(), FlutterwaveGateway)


def test_get_gateway_returns_real_stripe_when_configured():
    _configure_gateway(Gateway.STRIPE)
    gw = get_gateway()
    assert isinstance(gw, StripeGateway)
    assert gw.config is not None  # distinct from the legacy settings-fallback StripeGateway()


def test_flutterwave_initialize_converts_cents_to_major_units(monkeypatch):
    cfg = _configure_gateway(Gateway.FLUTTERWAVE)
    inv = _paid_invoice_setup(total_cents=5_000)  # $50.00
    gw = FlutterwaveGateway(cfg)
    captured = {}

    class _CapturingClient(_FakeHttpxClient):
        def post(self, path, json=None):
            captured["payload"] = json
            return self._responses["post"]

    fake = _CapturingClient(post=_FakeResponse(200, {
        "status": "success", "data": {"link": "https://checkout.flutterwave.com/xyz"},
    }))
    monkeypatch.setattr(gw, "_client", lambda: fake)
    attempt = _attempt_with_allocation(
        inv, gateway=Gateway.FLUTTERWAVE, reference="campus_fw", amount_cents=5_000
    )
    url, session_id = gw.initialize(invoices=[inv], attempt=attempt)
    assert url == "https://checkout.flutterwave.com/xyz"
    assert session_id == ""
    assert captured["payload"]["amount"] == 50.0  # 5000 cents -> 50.00 major units


def test_flutterwave_verify_converts_major_units_back_to_cents():
    cfg = _configure_gateway(Gateway.FLUTTERWAVE)
    gw = FlutterwaveGateway(cfg)
    result = _mock_verify(gw, _bare_attempt(Gateway.FLUTTERWAVE), status=200, data={
        "status": "successful", "amount": 50.0, "currency": "NGN", "payment_type": "card",
    }, envelope_status="success")
    assert result.status == "success"
    assert result.amount_cents == 5_000  # 50.00 major units -> 5000 cents


def test_flutterwave_verify_failed_and_pending():
    cfg = _configure_gateway(Gateway.FLUTTERWAVE)
    gw = FlutterwaveGateway(cfg)
    failed = _mock_verify(gw, _bare_attempt(Gateway.FLUTTERWAVE), status=200,
                          data={"status": "cancelled"}, envelope_status="success")
    assert failed.status == "failed"
    pending = _mock_verify(gw, _bare_attempt(Gateway.FLUTTERWAVE), status=200,
                           data={"status": "pending"}, envelope_status="success")
    assert pending.status == "pending"


def test_stripe_initialize_requires_a_return_url():
    cfg = _configure_gateway(Gateway.STRIPE)
    inv = _paid_invoice_setup()
    gw = StripeGateway(cfg)
    attempt = _attempt_with_allocation(
        inv, gateway=Gateway.STRIPE, reference="campus_stripe_no_url"
    )
    with pytest.raises(GatewayError):
        gw.initialize(invoices=[inv], attempt=attempt)  # no return_url


def test_stripe_initialize_success_returns_session_id(monkeypatch):
    cfg = _configure_gateway(Gateway.STRIPE)
    inv = _paid_invoice_setup(total_cents=2_500)
    gw = StripeGateway(cfg)
    fake = _FakeHttpxClient(post=_FakeResponse(200, {
        "id": "cs_test_abc123", "url": "https://checkout.stripe.com/c/pay/cs_test_abc123",
    }))
    monkeypatch.setattr(gw, "_client", lambda: fake)
    attempt = _attempt_with_allocation(
        inv, gateway=Gateway.STRIPE, reference="campus_stripe_ok", amount_cents=2_500
    )
    url, session_id = gw.initialize(
        invoices=[inv], attempt=attempt, return_url="https://school.example/return"
    )
    assert url == "https://checkout.stripe.com/c/pay/cs_test_abc123"
    assert session_id == "cs_test_abc123"


def test_stripe_verify_with_no_session_id_yet_is_pending():
    cfg = _configure_gateway(Gateway.STRIPE)
    gw = StripeGateway(cfg)
    attempt = _bare_attempt(Gateway.STRIPE, gateway_session_id="")
    result = gw.verify(attempt)
    assert result.status == "pending"


def test_stripe_verify_paid_session_is_success(monkeypatch):
    # Stripe's response is the session object itself, NOT wrapped in
    # {"status": ..., "data": ...} the way Paystack/Flutterwave are - a real
    # difference between the three, not an oversight, so this doesn't reuse
    # `_mock_verify`.
    cfg = _configure_gateway(Gateway.STRIPE)
    gw = StripeGateway(cfg)
    attempt = _bare_attempt(Gateway.STRIPE, gateway_session_id="cs_test_abc123")
    fake = _FakeHttpxClient(get=_FakeResponse(200, {
        "payment_status": "paid", "status": "complete",
        "amount_total": 2_500, "currency": "cad",
    }))
    monkeypatch.setattr(gw, "_client", lambda: fake)
    result = gw.verify(attempt)
    assert result.status == "success"
    assert result.amount_cents == 2_500
    assert result.currency == "CAD"


def test_stripe_verify_expired_session_is_failed(monkeypatch):
    cfg = _configure_gateway(Gateway.STRIPE)
    gw = StripeGateway(cfg)
    attempt = _bare_attempt(Gateway.STRIPE, gateway_session_id="cs_test_expired")
    fake = _FakeHttpxClient(get=_FakeResponse(200, {
        "payment_status": "unpaid", "status": "expired",
    }))
    monkeypatch.setattr(gw, "_client", lambda: fake)
    result = gw.verify(attempt)
    assert result.status == "failed"


# ---- services: initiate_online_payment / resolve_payment_attempt ----------

def test_initiate_online_payment_requires_a_real_online_gateway():
    inv = _paid_invoice_setup()  # GatewayConfig still MANUAL (default)
    with pytest.raises(GatewayNotConfigured):
        initiate_online_payment([inv])


def test_initiate_online_payment_creates_a_pending_attempt(monkeypatch):
    _configure_paystack()
    inv = _paid_invoice_setup(total_cents=3_000)
    monkeypatch.setattr(
        PaystackGateway, "initialize",
        lambda self, *, invoices, attempt, return_url="": ("https://checkout.paystack.com/abc", ""),
    )
    attempt = initiate_online_payment([inv])
    assert attempt.status == PaymentAttempt.Status.PENDING
    assert attempt.checkout_url == "https://checkout.paystack.com/abc"
    assert attempt.amount_cents == 3_000
    assert attempt.gateway == Gateway.PAYSTACK
    assert attempt.allocations.count() == 1
    assert attempt.allocations.get().allocated_cents == 3_000


def test_initiate_online_payment_rejects_a_fully_paid_invoice():
    _configure_paystack()
    inv = _paid_invoice_setup(total_cents=1_000)
    ManualGateway().charge(inv, 1_000, method=Payment.Method.CASH)
    with pytest.raises(ValueError):
        initiate_online_payment([inv])


def test_initiate_online_payment_rejects_invoices_from_different_guardians(monkeypatch):
    _configure_paystack()
    inv_a = _paid_invoice_setup(total_cents=2_000)
    inv_b = _paid_invoice_setup(total_cents=3_000)  # a different student/guardian entirely
    monkeypatch.setattr(
        PaystackGateway, "initialize",
        lambda self, *, invoices, attempt, return_url="": ("https://checkout.paystack.com/abc", ""),
    )
    with pytest.raises(ValueError, match="same guardian"):
        initiate_online_payment([inv_a, inv_b])


def test_initiate_online_payment_works_for_a_legacy_invoice_with_no_guardian_set(monkeypatch):
    """Real bug, found 2026-09-16: every invoice created before
    Invoice.save() started defaulting `guardian` at creation time has
    `guardian_id` NULL - and initiate_online_payment's guardian-
    consistency check used to read that raw column directly, so paying
    ANY such invoice (the vast majority of the live demo data at the
    time) failed with "must be billed to the same guardian" even for a
    single, uncombined invoice. Fixed via `Invoice.effective_guardian`
    (falls back to the primary-contact GuardianLink)."""
    _configure_paystack()
    kid = make_student()
    link_guardian(kid, email="legacy@example.test", is_primary_contact=True)
    inv = Invoice.objects.create(student=kid)
    InvoiceLine.objects.create(invoice=inv, description="fee", unit_amount_cents=3_000)
    issue_invoice(inv)
    # simulate a pre-2026-09-16 row: guardian_id never got backfilled
    Invoice.objects.filter(pk=inv.pk).update(guardian=None)
    inv.refresh_from_db()
    assert inv.guardian_id is None

    monkeypatch.setattr(
        PaystackGateway, "initialize",
        lambda self, *, invoices, attempt, return_url="": (
            "https://checkout.paystack.com/legacy", ""
        ),
    )
    attempt = initiate_online_payment([inv])
    assert attempt.status == PaymentAttempt.Status.PENDING
    assert attempt.amount_cents == 3_000


def test_initiate_online_payment_combines_siblings_into_one_attempt(monkeypatch):
    _configure_paystack()
    kid1 = make_student()
    kid2 = make_student()
    guardian_link = link_guardian(kid1, email="family@example.test", is_primary_contact=True)
    GuardianLink.objects.create(
        student=kid2, guardian=guardian_link.guardian, is_primary_contact=True,
        relationship=GuardianLink.Relationship.PARENT,
    )
    inv1 = Invoice.objects.create(student=kid1)
    InvoiceLine.objects.create(invoice=inv1, description="fee", unit_amount_cents=3_000)
    inv2 = Invoice.objects.create(student=kid2)
    InvoiceLine.objects.create(invoice=inv2, description="fee", unit_amount_cents=1_000)
    issue_invoice(inv1)
    issue_invoice(inv2)
    assert inv1.guardian_id == inv2.guardian_id  # both defaulted to the shared primary contact

    monkeypatch.setattr(
        PaystackGateway, "initialize",
        lambda self, *, invoices, attempt, return_url="": (
            "https://checkout.paystack.com/combo", ""
        ),
    )
    attempt = initiate_online_payment([inv1, inv2])
    assert attempt.amount_cents == 4_000
    allocations = {a.invoice_id: a.allocated_cents for a in attempt.allocations.all()}
    assert allocations == {inv1.pk: 3_000, inv2.pk: 1_000}


def test_initiate_online_payment_allows_a_smaller_custom_amount(monkeypatch):
    _configure_paystack()
    inv = _paid_invoice_setup(total_cents=10_000)
    monkeypatch.setattr(
        PaystackGateway, "initialize",
        lambda self, *, invoices, attempt, return_url="": (
            "https://checkout.paystack.com/partial", ""
        ),
    )
    attempt = initiate_online_payment([inv], amount_cents=4_000)
    assert attempt.amount_cents == 4_000
    assert attempt.allocations.get().allocated_cents == 4_000


def test_initiate_online_payment_rejects_a_custom_amount_over_the_balance():
    _configure_paystack()
    inv = _paid_invoice_setup(total_cents=1_000)
    with pytest.raises(ValueError):
        initiate_online_payment([inv], amount_cents=2_000)


# ---- services: allocate_payment (largest-remainder proportional split) ----

def test_allocate_payment_splits_the_full_balance_exactly():
    inv1 = _paid_invoice_setup(total_cents=3_000)
    inv2 = _paid_invoice_setup(total_cents=1_000)
    allocations = allocate_payment([inv1, inv2], 4_000)
    assert dict((inv.pk, cents) for inv, cents in allocations) == {inv1.pk: 3_000, inv2.pk: 1_000}


def test_allocate_payment_splits_a_partial_amount_proportionally_and_sums_exactly():
    inv1 = _paid_invoice_setup(total_cents=1_000)  # weight 1
    inv2 = _paid_invoice_setup(total_cents=2_000)  # weight 2
    inv3 = _paid_invoice_setup(total_cents=3_000)  # weight 3, total weight 6
    # 1000 / 6 doesn't divide evenly - exercises the largest-remainder path.
    allocations = allocate_payment([inv1, inv2, inv3], 1_000)
    cents = [c for _inv, c in allocations]
    assert sum(cents) == 1_000  # never off by a cent, however the rounding falls
    # proportional: inv3 (heaviest) gets the largest share, inv1 the smallest.
    assert cents[2] >= cents[1] >= cents[0]


def test_resolve_payment_attempt_success_creates_a_gateway_payment(monkeypatch):
    _configure_paystack()
    inv = _paid_invoice_setup(total_cents=4_000)
    attempt = _attempt_with_allocation(
        inv, gateway=Gateway.PAYSTACK, reference="campus_ok",
        status=PaymentAttempt.Status.PENDING,
    )
    monkeypatch.setattr(
        PaystackGateway, "verify",
        lambda self, attempt: VerifiedResult(
            status="success", amount_cents=4_000, currency=inv.currency,
            channel="card", raw={"ok": True},
        ),
    )
    resolved = resolve_payment_attempt(attempt)
    assert resolved.status == PaymentAttempt.Status.SUCCESS
    inv.refresh_from_db()
    assert inv.status == Invoice.Status.PAID
    payment = Payment.objects.get(gateway_reference="campus_ok")
    assert payment.source == Payment.Source.GATEWAY
    assert payment.amount_cents == 4_000


def test_resolve_payment_attempt_success_splits_across_combined_invoices(monkeypatch):
    _configure_paystack()
    inv1 = _paid_invoice_setup(total_cents=3_000)
    inv2 = _paid_invoice_setup(total_cents=1_000)
    attempt = PaymentAttempt.objects.create(
        gateway=Gateway.PAYSTACK, reference="campus_combo",
        amount_cents=4_000, currency=inv1.currency, status=PaymentAttempt.Status.PENDING,
    )
    PaymentAttemptInvoice.objects.create(attempt=attempt, invoice=inv1, allocated_cents=3_000)
    PaymentAttemptInvoice.objects.create(attempt=attempt, invoice=inv2, allocated_cents=1_000)
    monkeypatch.setattr(
        PaystackGateway, "verify",
        lambda self, attempt: VerifiedResult(
            status="success", amount_cents=4_000, currency=inv1.currency, channel="card", raw={},
        ),
    )
    resolved = resolve_payment_attempt(attempt)
    assert resolved.status == PaymentAttempt.Status.SUCCESS
    inv1.refresh_from_db()
    inv2.refresh_from_db()
    assert inv1.status == Invoice.Status.PAID
    assert inv2.status == Invoice.Status.PAID
    payments = Payment.objects.filter(gateway_reference="campus_combo")
    assert payments.count() == 2
    assert {p.invoice_id: p.amount_cents for p in payments} == {inv1.pk: 3_000, inv2.pk: 1_000}


def test_resolve_payment_attempt_mismatch_does_not_create_a_payment(monkeypatch):
    _configure_paystack()
    inv = _paid_invoice_setup(total_cents=4_000)
    attempt = _attempt_with_allocation(
        inv, gateway=Gateway.PAYSTACK, reference="campus_mismatch",
        status=PaymentAttempt.Status.PENDING,
    )
    monkeypatch.setattr(
        PaystackGateway, "verify",
        lambda self, attempt: VerifiedResult(
            status="success", amount_cents=1, currency=inv.currency, channel="card", raw={}
        ),
    )
    resolved = resolve_payment_attempt(attempt)
    assert resolved.status == PaymentAttempt.Status.MISMATCH
    assert not Payment.objects.filter(gateway_reference="campus_mismatch").exists()
    inv.refresh_from_db()
    assert inv.status == Invoice.Status.ISSUED


def test_resolve_payment_attempt_failed(monkeypatch):
    _configure_paystack()
    inv = _paid_invoice_setup()
    attempt = _attempt_with_allocation(
        inv, gateway=Gateway.PAYSTACK, reference="campus_fail",
        status=PaymentAttempt.Status.PENDING,
    )
    monkeypatch.setattr(
        PaystackGateway, "verify",
        lambda self, attempt: VerifiedResult(
            status="failed", amount_cents=None, currency=None, channel="", raw={},
        ),
    )
    resolved = resolve_payment_attempt(attempt)
    assert resolved.status == PaymentAttempt.Status.FAILED


def test_resolve_payment_attempt_terminal_status_never_calls_the_gateway(monkeypatch):
    _configure_paystack()
    inv = _paid_invoice_setup()
    attempt = _attempt_with_allocation(
        inv, gateway=Gateway.PAYSTACK, reference="campus_done",
        status=PaymentAttempt.Status.SUCCESS,
    )

    def _boom(self, attempt):
        raise AssertionError("verify() should never be called for a resolved attempt")

    monkeypatch.setattr(PaystackGateway, "verify", _boom)
    resolved = resolve_payment_attempt(attempt)
    assert resolved.status == PaymentAttempt.Status.SUCCESS


# ---- API: POST /api/invoices/pay/, GET /api/payment-attempts/{ref}/ ------

def test_api_parent_can_start_a_checkout(auth_client, make_user, monkeypatch):
    _configure_paystack()
    kid = make_student()
    parent_user = make_user(username="payparent", role="PARENT")
    link_guardian(kid, user=parent_user, email="payparent@example.test", is_primary_contact=True)
    inv = Invoice.objects.create(student=kid)
    InvoiceLine.objects.create(invoice=inv, description="fee", unit_amount_cents=2_000)
    issue_invoice(inv)

    monkeypatch.setattr(
        PaystackGateway, "initialize",
        lambda self, *, invoices, attempt, return_url="": ("https://checkout.paystack.com/xyz", ""),
    )
    client = auth_client(parent_user)
    resp = client.post("/api/invoices/pay/", {"invoice_ids": [str(inv.pk)]}, format="json")
    assert resp.status_code == 201
    assert resp.data["checkout_url"] == "https://checkout.paystack.com/xyz"
    assert resp.data["status"] == "PENDING"
    assert len(resp.data["allocations"]) == 1
    assert resp.data["allocations"][0]["allocated_cents"] == 2_000


def test_api_parent_can_pay_a_legacy_invoice_with_no_guardian_set(
    auth_client, make_user, monkeypatch
):
    """The exact bug Damien hit live: a real invoice from before the
    guardian-default fix, guardian_id NULL - the view's own parent-
    ownership check used the raw column too, so this 403'd for the
    correct guardian ("You may only pay invoices billed to you.")."""
    _configure_paystack()
    kid = make_student()
    parent_user = make_user(username="legacyparent", role="PARENT")
    link_guardian(kid, user=parent_user, email="legacyparent@example.test", is_primary_contact=True)
    inv = Invoice.objects.create(student=kid)
    InvoiceLine.objects.create(invoice=inv, description="fee", unit_amount_cents=1_500)
    issue_invoice(inv)
    Invoice.objects.filter(pk=inv.pk).update(guardian=None)

    monkeypatch.setattr(
        PaystackGateway, "initialize",
        lambda self, *, invoices, attempt, return_url="": (
            "https://checkout.paystack.com/legacy", ""
        ),
    )
    client = auth_client(parent_user)
    resp = client.post("/api/invoices/pay/", {"invoice_ids": [str(inv.pk)]}, format="json")
    assert resp.status_code == 201


def test_api_parent_can_combine_two_childrens_invoices(auth_client, make_user, monkeypatch):
    _configure_paystack()
    kid1 = make_student()
    kid2 = make_student()
    parent_user = make_user(username="combineparent", role="PARENT")
    link = link_guardian(
        kid1, user=parent_user, email="combineparent@example.test", is_primary_contact=True
    )
    GuardianLink.objects.create(
        student=kid2, guardian=link.guardian, is_primary_contact=True,
        relationship=GuardianLink.Relationship.PARENT,
    )
    inv1 = Invoice.objects.create(student=kid1)
    InvoiceLine.objects.create(invoice=inv1, description="fee", unit_amount_cents=2_000)
    inv2 = Invoice.objects.create(student=kid2)
    InvoiceLine.objects.create(invoice=inv2, description="fee", unit_amount_cents=1_000)
    issue_invoice(inv1)
    issue_invoice(inv2)

    monkeypatch.setattr(
        PaystackGateway, "initialize",
        lambda self, *, invoices, attempt, return_url="": (
            "https://checkout.paystack.com/combo", ""
        ),
    )
    client = auth_client(parent_user)
    resp = client.post(
        "/api/invoices/pay/", {"invoice_ids": [str(inv1.pk), str(inv2.pk)]}, format="json"
    )
    assert resp.status_code == 201
    assert resp.data["amount_cents"] == 3_000
    assert len(resp.data["allocations"]) == 2


def test_api_parent_cannot_combine_someone_elses_invoice(auth_client, make_user):
    _configure_paystack()
    kid = make_student()
    other_kid = make_student()
    parent_user = make_user(username="onlymine", role="PARENT")
    link_guardian(kid, user=parent_user, email="onlymine@example.test", is_primary_contact=True)
    link_guardian(other_kid, email="stranger@example.test", is_primary_contact=True)
    mine = Invoice.objects.create(student=kid)
    InvoiceLine.objects.create(invoice=mine, description="fee", unit_amount_cents=1_000)
    not_mine = Invoice.objects.create(student=other_kid)
    InvoiceLine.objects.create(invoice=not_mine, description="fee", unit_amount_cents=1_000)
    issue_invoice(mine)
    issue_invoice(not_mine)

    client = auth_client(parent_user)
    resp = client.post(
        "/api/invoices/pay/", {"invoice_ids": [str(mine.pk), str(not_mine.pk)]}, format="json"
    )
    assert resp.status_code == 403


def test_api_front_office_can_generate_a_link_for_a_familys_invoices(
    auth_client, admin_user, monkeypatch
):
    _configure_paystack()
    kid1 = make_student()
    kid2 = make_student()
    link = link_guardian(kid1, email="office@example.test", is_primary_contact=True)
    GuardianLink.objects.create(
        student=kid2, guardian=link.guardian, is_primary_contact=True,
        relationship=GuardianLink.Relationship.PARENT,
    )
    inv1 = Invoice.objects.create(student=kid1)
    InvoiceLine.objects.create(invoice=inv1, description="fee", unit_amount_cents=2_000)
    inv2 = Invoice.objects.create(student=kid2)
    InvoiceLine.objects.create(invoice=inv2, description="fee", unit_amount_cents=1_000)
    issue_invoice(inv1)
    issue_invoice(inv2)

    monkeypatch.setattr(
        PaystackGateway, "initialize",
        lambda self, *, invoices, attempt, return_url="": (
            "https://checkout.paystack.com/link", ""
        ),
    )
    client = auth_client(admin_user)
    resp = client.post(
        "/api/invoices/pay/", {"invoice_ids": [str(inv1.pk), str(inv2.pk)]}, format="json"
    )
    assert resp.status_code == 201
    assert resp.data["amount_cents"] == 3_000


def test_api_pay_allows_a_smaller_custom_amount(auth_client, make_user, monkeypatch):
    _configure_paystack()
    kid = make_student()
    parent_user = make_user(username="partialparent", role="PARENT")
    link_guardian(
        kid, user=parent_user, email="partialparent@example.test", is_primary_contact=True
    )
    inv = Invoice.objects.create(student=kid)
    InvoiceLine.objects.create(invoice=inv, description="fee", unit_amount_cents=10_000)
    issue_invoice(inv)

    monkeypatch.setattr(
        PaystackGateway, "initialize",
        lambda self, *, invoices, attempt, return_url="": (
            "https://checkout.paystack.com/small", ""
        ),
    )
    client = auth_client(parent_user)
    resp = client.post(
        "/api/invoices/pay/",
        {"invoice_ids": [str(inv.pk)], "amount_cents": 4_000},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["amount_cents"] == 4_000


def test_api_teacher_cannot_start_a_checkout(auth_client, staff):
    _configure_paystack()
    inv = _paid_invoice_setup()
    client = auth_client(staff)
    resp = client.post("/api/invoices/pay/", {"invoice_ids": [str(inv.pk)]}, format="json")
    assert resp.status_code == 403


def test_api_pay_returns_409_when_no_gateway_configured(auth_client, admin_user):
    inv = _paid_invoice_setup()  # GatewayConfig still MANUAL
    client = auth_client(admin_user)
    resp = client.post("/api/invoices/pay/", {"invoice_ids": [str(inv.pk)]}, format="json")
    assert resp.status_code == 409


def test_api_payment_attempt_lookup_resolves_live(auth_client, admin_user, monkeypatch):
    _configure_paystack()
    inv = _paid_invoice_setup(total_cents=2_500)
    attempt = _attempt_with_allocation(
        inv, gateway=Gateway.PAYSTACK, reference="campus_api_ok",
        status=PaymentAttempt.Status.PENDING,
    )
    monkeypatch.setattr(
        PaystackGateway, "verify",
        lambda self, attempt: VerifiedResult(
            status="success", amount_cents=2_500, currency=inv.currency, channel="card", raw={}
        ),
    )
    client = auth_client(admin_user)
    resp = client.get(f"/api/payment-attempts/{attempt.reference}/")
    assert resp.status_code == 200
    assert resp.data["status"] == "SUCCESS"


# ---- management commands: set_gateway_config, payments_test --------------

def test_set_gateway_config_command():
    call_command(
        "set_gateway_config", gateway="paystack", mode="test",
        public_key="pk_test_x", secret_key="sk_test_x",
    )
    cfg = GatewayConfig.load()
    assert cfg.gateway == Gateway.PAYSTACK and cfg.mode == GatewayConfig.Mode.TEST
    assert cfg.secret_key == "sk_test_x"


def test_set_gateway_config_requires_keys_for_a_real_gateway():
    with pytest.raises(CommandError):
        call_command("set_gateway_config", gateway="paystack")


def test_payments_test_command_uses_saved_config_by_default(monkeypatch):
    _configure_paystack()
    monkeypatch.setattr(PaystackGateway, "test_connection", lambda self: (True, "ok"))
    call_command("payments_test")  # raises on failure - not raising is the assertion


def test_payments_test_command_fails_when_nothing_configured():
    with pytest.raises(CommandError, match="manual only"):
        call_command("payments_test")


def test_payments_test_command_tests_unsaved_override_values(monkeypatch):
    # GatewayConfig stays MANUAL the whole time - the override args are
    # tested WITHOUT ever being saved. This is exactly what the GUI's Test
    # Connection button relies on (test before Apply).
    captured_config = {}

    def _fake_test_connection(self):
        captured_config["gateway"] = self.config.gateway
        return True, "ok"

    monkeypatch.setattr(PaystackGateway, "test_connection", _fake_test_connection)
    call_command(
        "payments_test", gateway="paystack", mode="test",
        public_key="pk_test_x", secret_key="sk_test_x",
    )
    assert captured_config["gateway"] == Gateway.PAYSTACK
    # `GatewayConfig(...)` gets a UUID pk at construction (UUIDField default),
    # not at .save() - so "never saved" has to be checked against the table,
    # not the instance's own .pk.
    assert GatewayConfig.objects.count() == 0  # the tested config was never written


def test_payments_test_command_override_requires_keys():
    with pytest.raises(CommandError):
        call_command("payments_test", gateway="paystack")


def test_api_payment_attempt_hides_no_raw_response_field(auth_client, admin_user):
    _configure_paystack()
    inv = _paid_invoice_setup()
    attempt = _attempt_with_allocation(inv, gateway=Gateway.PAYSTACK, reference="campus_shape")
    client = auth_client(admin_user)
    resp = client.get(f"/api/payment-attempts/{attempt.reference}/")
    assert "raw_response" not in resp.data


def _invoice(total_cents=10_000) -> Invoice:
    kid = make_student()
    inv = Invoice.objects.create(student=kid)
    InvoiceLine.objects.create(invoice=inv, description="Term fee", quantity=1,
                               unit_amount_cents=total_cents)
    return inv


def test_invoice_totals_and_balance():
    inv = _invoice(total_cents=15_000)
    assert inv.total_cents == 15_000
    assert inv.paid_cents == 0
    assert inv.balance_cents == 15_000


def test_manual_gateway_records_a_payment_and_updates_status(superadmin):
    inv = _invoice(total_cents=10_000)
    issue_invoice(inv, actor=superadmin)

    ManualGateway().charge(inv, 4_000, method=Payment.Method.E_TRANSFER,
                           reference="ETRF123", received_by=superadmin)
    inv.refresh_from_db()
    assert inv.status == Invoice.Status.PARTIALLY_PAID
    assert inv.paid_cents == 4_000

    ManualGateway().charge(inv, 6_000, method=Payment.Method.CASH, received_by=superadmin)
    inv.refresh_from_db()
    assert inv.status == Invoice.Status.PAID
    assert inv.balance_cents == 0
    assert Payment.objects.filter(invoice=inv).count() == 2


def test_manual_gateway_refund_is_not_automatic():
    inv = _invoice()
    payment = ManualGateway().charge(inv, 1000, method=Payment.Method.CASH)
    with pytest.raises(NotImplementedError):
        ManualGateway().refund(payment, 1000)


def test_stripe_gateway_is_a_stub():
    inv = _invoice()
    with pytest.raises(NotImplementedError):
        StripeGateway().charge(inv, 1000)
    payment = ManualGateway().charge(inv, 1000, method=Payment.Method.CASH)
    with pytest.raises(NotImplementedError):
        StripeGateway().refund(payment, 1000)


def test_get_gateway_defaults_to_manual(settings):
    settings.FEATURE_PAYMENTS_GATEWAY = "manual"
    assert isinstance(get_gateway(), ManualGateway)
    settings.FEATURE_PAYMENTS_GATEWAY = "stripe"
    assert isinstance(get_gateway(), StripeGateway)


def test_void_invoice_blocks_further_payment():
    inv = _invoice()
    void_invoice(inv, reason="duplicate")
    inv.refresh_from_db()
    assert inv.status == Invoice.Status.VOID
    with pytest.raises(ValueError):
        mark_paid(inv, amount_cents=100, method=Payment.Method.CASH)


def test_portal_summary_excludes_drafts_and_has_no_card_fields():
    inv = _invoice(total_cents=5_000)
    assert portal_summary(inv.student) == []  # still DRAFT
    issue_invoice(inv)
    rows = portal_summary(inv.student)
    assert len(rows) == 1
    assert set(rows[0]) == {"id", "status", "total_cents", "balance_cents", "due_date"}


def test_credit_is_scoped_like_a_student_record():
    kid = make_student()
    Credit.objects.create(student=kid, amount_cents=500, reason="goodwill")
    assert Credit.objects.filter(student=kid).exists()


def test_api_front_office_issues_and_marks_paid(auth_client, admin_user):
    inv = _invoice(total_cents=2_000)
    client = auth_client(admin_user)
    issued = client.post(f"/api/invoices/{inv.pk}/issue/")
    assert issued.status_code == 200 and issued.data["status"] == "ISSUED"

    paid = client.post(f"/api/invoices/{inv.pk}/mark-paid/", {
        "amount_cents": 2000, "method": "CASH",
    }, format="json")
    assert paid.status_code == 201
    assert paid.data["invoice"]["status"] == "PAID"


def test_api_teacher_has_no_billing_access(auth_client, staff):
    inv = _invoice()
    client = auth_client(staff)
    assert client.get("/api/invoices/").status_code == 403
    assert client.post(f"/api/invoices/{inv.pk}/issue/").status_code == 403


def test_api_parent_reads_only_their_childs_issued_invoices(auth_client, make_user, admin_user):
    kid = make_student()
    other_kid = make_student()
    parent = make_user(username="billparent", role="PARENT")
    link_guardian(kid, user=parent, is_primary_contact=True)

    mine = Invoice.objects.create(student=kid)
    InvoiceLine.objects.create(invoice=mine, description="fee", unit_amount_cents=1000)
    theirs = Invoice.objects.create(student=other_kid)
    InvoiceLine.objects.create(invoice=theirs, description="fee", unit_amount_cents=1000)

    office = auth_client(admin_user)
    office.post(f"/api/invoices/{mine.pk}/issue/")
    office.post(f"/api/invoices/{theirs.pk}/issue/")

    parent_client = auth_client(parent)
    resp = parent_client.get("/api/invoices/")
    assert resp.status_code == 200
    ids = {str(row["id"]) for row in resp.data["results"]}
    assert ids == {str(mine.pk)}
    # object-level: the specific billing guardian can open their own invoice
    assert parent_client.get(f"/api/invoices/{mine.pk}/").status_code == 200
    # a parent cannot mark their own invoice paid
    assert parent_client.post(f"/api/invoices/{mine.pk}/mark-paid/",
                              {"amount_cents": 1000, "method": "CASH"},
                              format="json").status_code == 403


def test_invoice_is_not_visible_to_a_guardian_linked_but_not_billed(auth_client, make_user):
    """The gap closed alongside multi-child invoicing (2026-09-16): a
    non-custodial/estranged co-parent (or a step-parent with no financial
    role) may be linked to a child without being the guardian an invoice is
    actually billed to - `is_visible_to` must key off that specific
    billing relationship, not "any guardian linked to this student.\""""
    kid = make_student()
    billing_parent = make_user(username="billingparent", role="PARENT")
    other_parent = make_user(username="estrangedparent", role="PARENT")
    link_guardian(kid, user=billing_parent, is_primary_contact=True)
    link_guardian(kid, user=other_parent, is_primary_contact=False)  # linked, not the payer

    invoice = Invoice.objects.create(student=kid)
    InvoiceLine.objects.create(invoice=invoice, description="fee", unit_amount_cents=1_000)
    issue_invoice(invoice)
    assert invoice.guardian.user_id == billing_parent.pk  # defaulted to the primary contact

    billed_client = auth_client(billing_parent)
    assert billed_client.get(f"/api/invoices/{invoice.pk}/").status_code == 200

    other_client = auth_client(other_parent)
    # Still in the parent-role queryset (linked to the same student), but
    # `IsObjectOwnerOrStaff` denies it via the tightened `is_visible_to` -
    # a 403, not a 404 (the object IS visible enough to be found, just not
    # to be opened).
    assert other_client.get(f"/api/invoices/{invoice.pk}/").status_code == 403


def test_fee_schedule_display_string_uses_dollars():
    fs = FeeSchedule.objects.create(name="Registration", amount_cents=12_345)
    assert "$123.45" in str(fs)


def test_api_invoice_search_matches_a_full_first_and_last_name(auth_client, admin_user):
    """Damien, 2026-09-16: an issued invoice existed for "Uriah Oliver" but
    the console couldn't find it by searching that name - first_name and
    last_name are separate columns, so a single icontains(whole query)
    check against either one alone never matched a two-word name."""
    kid = make_student(first_name="Uriah", last_name="Oliver")
    mine = Invoice.objects.create(student=kid)
    InvoiceLine.objects.create(invoice=mine, description="fee", unit_amount_cents=1_000)
    issue_invoice(mine)
    other = _invoice(total_cents=5_000)  # an unrelated student/invoice - not a match
    issue_invoice(other)

    client = auth_client(admin_user)
    resp = client.get("/api/invoices/?q=Uriah+Oliver")
    assert resp.status_code == 200
    ids = {str(row["id"]) for row in resp.data["results"]}
    assert ids == {str(mine.pk)}
