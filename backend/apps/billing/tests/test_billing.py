from __future__ import annotations

import pytest

from apps.billing.gateways import (
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
)
from apps.billing.services import (
    initiate_online_payment,
    issue_invoice,
    mark_paid,
    portal_summary,
    resolve_payment_attempt,
    void_invoice,
)
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

    def post(self, path, json=None):
        return self._responses["post"]

    def get(self, path, params=None):
        return self._responses["get"]


def _configure_paystack(secret="sk_test_abc", public="pk_test_abc"):
    cfg = GatewayConfig.load()
    cfg.gateway = Gateway.PAYSTACK
    cfg.mode = GatewayConfig.Mode.TEST
    cfg.secret_key = secret
    cfg.public_key = public
    cfg.save()
    return cfg


def _paid_invoice_setup(total_cents=5_000):
    kid = make_student()
    link_guardian(kid, email="parent@example.test", is_primary_contact=True)
    inv = Invoice.objects.create(student=kid)
    InvoiceLine.objects.create(invoice=inv, description="Term fee", unit_amount_cents=total_cents)
    issue_invoice(inv)
    return inv


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
    attempt = PaymentAttempt.objects.create(
        invoice=inv, gateway=Gateway.PAYSTACK, reference="campus_x",
        amount_cents=inv.balance_cents, currency=inv.currency,
    )
    url = gw.initialize(invoice=inv, attempt=attempt)
    assert url == "https://checkout.paystack.com/xyz"


def test_paystack_initialize_without_guardian_email_raises():
    cfg = _configure_paystack()
    kid = make_student()  # no guardian linked at all
    inv = Invoice.objects.create(student=kid)
    InvoiceLine.objects.create(invoice=inv, description="fee", unit_amount_cents=1000)
    issue_invoice(inv)
    gw = PaystackGateway(cfg)
    attempt = PaymentAttempt.objects.create(
        invoice=inv, gateway=Gateway.PAYSTACK, reference="campus_y",
        amount_cents=inv.balance_cents, currency=inv.currency,
    )
    with pytest.raises(GatewayError):
        gw.initialize(invoice=inv, attempt=attempt)


def test_paystack_initialize_rejects_a_paystack_error(monkeypatch):
    cfg = _configure_paystack()
    inv = _paid_invoice_setup()
    gw = PaystackGateway(cfg)
    fake = _FakeHttpxClient(post=_FakeResponse(401, {"status": False, "message": "Invalid key"}))
    monkeypatch.setattr(gw, "_client", lambda: fake)
    attempt = PaymentAttempt.objects.create(
        invoice=inv, gateway=Gateway.PAYSTACK, reference="campus_z",
        amount_cents=inv.balance_cents, currency=inv.currency,
    )
    with pytest.raises(GatewayError):
        gw.initialize(invoice=inv, attempt=attempt)


def test_paystack_verify_success():
    cfg = _configure_paystack()
    gw = PaystackGateway(cfg)
    result = _mock_verify(gw, status=200, data={
        "status": "success", "amount": 5000, "currency": "ZAR", "channel": "card",
    })
    assert result.status == "success"
    assert result.amount_cents == 5000


def test_paystack_verify_pending():
    cfg = _configure_paystack()
    gw = PaystackGateway(cfg)
    result = _mock_verify(gw, status=200, data={"status": "pay_offline"})
    assert result.status == "pending"


def test_paystack_verify_failed():
    cfg = _configure_paystack()
    gw = PaystackGateway(cfg)
    result = _mock_verify(gw, status=200, data={"status": "abandoned"})
    assert result.status == "failed"


def _mock_verify(gw, *, status, data) -> VerifiedResult:
    mp = pytest.MonkeyPatch()
    try:
        fake = _FakeHttpxClient(get=_FakeResponse(status, {"status": True, "data": data}))
        mp.setattr(gw, "_client", lambda: fake)
        return gw.verify("some-reference")
    finally:
        mp.undo()


# ---- services: initiate_online_payment / resolve_payment_attempt ----------

def test_initiate_online_payment_requires_a_real_online_gateway():
    inv = _paid_invoice_setup()  # GatewayConfig still MANUAL (default)
    with pytest.raises(GatewayNotConfigured):
        initiate_online_payment(inv)


def test_initiate_online_payment_creates_a_pending_attempt(monkeypatch):
    _configure_paystack()
    inv = _paid_invoice_setup(total_cents=3_000)
    monkeypatch.setattr(
        PaystackGateway, "initialize",
        lambda self, *, invoice, attempt, return_url="": "https://checkout.paystack.com/abc",
    )
    attempt = initiate_online_payment(inv)
    assert attempt.status == PaymentAttempt.Status.PENDING
    assert attempt.checkout_url == "https://checkout.paystack.com/abc"
    assert attempt.amount_cents == 3_000
    assert attempt.gateway == Gateway.PAYSTACK


def test_initiate_online_payment_rejects_a_fully_paid_invoice():
    _configure_paystack()
    inv = _paid_invoice_setup(total_cents=1_000)
    ManualGateway().charge(inv, 1_000, method=Payment.Method.CASH)
    with pytest.raises(ValueError):
        initiate_online_payment(inv)


def test_resolve_payment_attempt_success_creates_a_gateway_payment(monkeypatch):
    _configure_paystack()
    inv = _paid_invoice_setup(total_cents=4_000)
    attempt = PaymentAttempt.objects.create(
        invoice=inv, gateway=Gateway.PAYSTACK, reference="campus_ok",
        amount_cents=4_000, currency=inv.currency, status=PaymentAttempt.Status.PENDING,
    )
    monkeypatch.setattr(
        PaystackGateway, "verify",
        lambda self, reference: VerifiedResult(
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


def test_resolve_payment_attempt_mismatch_does_not_create_a_payment(monkeypatch):
    _configure_paystack()
    inv = _paid_invoice_setup(total_cents=4_000)
    attempt = PaymentAttempt.objects.create(
        invoice=inv, gateway=Gateway.PAYSTACK, reference="campus_mismatch",
        amount_cents=4_000, currency=inv.currency, status=PaymentAttempt.Status.PENDING,
    )
    monkeypatch.setattr(
        PaystackGateway, "verify",
        lambda self, reference: VerifiedResult(
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
    attempt = PaymentAttempt.objects.create(
        invoice=inv, gateway=Gateway.PAYSTACK, reference="campus_fail",
        amount_cents=inv.balance_cents, currency=inv.currency, status=PaymentAttempt.Status.PENDING,
    )
    monkeypatch.setattr(
        PaystackGateway, "verify",
        lambda self, reference: VerifiedResult(
            status="failed", amount_cents=None, currency=None, channel="", raw={},
        ),
    )
    resolved = resolve_payment_attempt(attempt)
    assert resolved.status == PaymentAttempt.Status.FAILED


def test_resolve_payment_attempt_terminal_status_never_calls_the_gateway(monkeypatch):
    _configure_paystack()
    inv = _paid_invoice_setup()
    attempt = PaymentAttempt.objects.create(
        invoice=inv, gateway=Gateway.PAYSTACK, reference="campus_done",
        amount_cents=inv.balance_cents, currency=inv.currency, status=PaymentAttempt.Status.SUCCESS,
    )

    def _boom(self, reference):
        raise AssertionError("verify() should never be called for a resolved attempt")

    monkeypatch.setattr(PaystackGateway, "verify", _boom)
    resolved = resolve_payment_attempt(attempt)
    assert resolved.status == PaymentAttempt.Status.SUCCESS


# ---- API: POST /api/invoices/{id}/pay/, GET /api/payment-attempts/{ref}/ --

def test_api_parent_can_start_a_checkout(auth_client, make_user, monkeypatch):
    _configure_paystack()
    kid = make_student()
    parent_user = make_user(username="payparent", role="PARENT")
    link_guardian(kid, user=parent_user, email="payparent@example.test")
    inv = Invoice.objects.create(student=kid)
    InvoiceLine.objects.create(invoice=inv, description="fee", unit_amount_cents=2_000)
    issue_invoice(inv)

    monkeypatch.setattr(
        PaystackGateway, "initialize",
        lambda self, *, invoice, attempt, return_url="": "https://checkout.paystack.com/xyz",
    )
    client = auth_client(parent_user)
    resp = client.post(f"/api/invoices/{inv.pk}/pay/")
    assert resp.status_code == 201
    assert resp.data["checkout_url"] == "https://checkout.paystack.com/xyz"
    assert resp.data["status"] == "PENDING"


def test_api_teacher_cannot_start_a_checkout(auth_client, staff):
    _configure_paystack()
    inv = _paid_invoice_setup()
    client = auth_client(staff)
    assert client.post(f"/api/invoices/{inv.pk}/pay/").status_code == 403


def test_api_pay_returns_409_when_no_gateway_configured(auth_client, admin_user):
    inv = _paid_invoice_setup()  # GatewayConfig still MANUAL
    client = auth_client(admin_user)
    resp = client.post(f"/api/invoices/{inv.pk}/pay/")
    assert resp.status_code == 409


def test_api_payment_attempt_lookup_resolves_live(auth_client, admin_user, monkeypatch):
    _configure_paystack()
    inv = _paid_invoice_setup(total_cents=2_500)
    attempt = PaymentAttempt.objects.create(
        invoice=inv, gateway=Gateway.PAYSTACK, reference="campus_api_ok",
        amount_cents=2_500, currency=inv.currency, status=PaymentAttempt.Status.PENDING,
    )
    monkeypatch.setattr(
        PaystackGateway, "verify",
        lambda self, reference: VerifiedResult(
            status="success", amount_cents=2_500, currency=inv.currency, channel="card", raw={}
        ),
    )
    client = auth_client(admin_user)
    resp = client.get(f"/api/payment-attempts/{attempt.reference}/")
    assert resp.status_code == 200
    assert resp.data["status"] == "SUCCESS"


def test_api_payment_attempt_hides_no_raw_response_field(auth_client, admin_user):
    _configure_paystack()
    inv = _paid_invoice_setup()
    attempt = PaymentAttempt.objects.create(
        invoice=inv, gateway=Gateway.PAYSTACK, reference="campus_shape",
        amount_cents=inv.balance_cents, currency=inv.currency,
    )
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
    link_guardian(kid, user=parent)

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
    # a parent cannot mark their own invoice paid
    assert parent_client.post(f"/api/invoices/{mine.pk}/mark-paid/",
                              {"amount_cents": 1000, "method": "CASH"},
                              format="json").status_code == 403


def test_fee_schedule_display_string_uses_dollars():
    fs = FeeSchedule.objects.create(name="Registration", amount_cents=12_345)
    assert "$123.45" in str(fs)
