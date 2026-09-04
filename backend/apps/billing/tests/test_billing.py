from __future__ import annotations

import pytest

from apps.billing.gateways import ManualGateway, StripeGateway, get_gateway
from apps.billing.models import Credit, FeeSchedule, Invoice, InvoiceLine, Payment
from apps.billing.services import issue_invoice, mark_paid, portal_summary, void_invoice
from apps.people.tests.factories import link_guardian, make_student

pytestmark = pytest.mark.django_db


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
