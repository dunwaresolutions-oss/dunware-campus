"""SiteConfiguration — the singleton, /api/config/, currency lock, and the
fee-collection toggle that closes the Billing area."""
from __future__ import annotations

import pytest
from django.core.management import call_command

from apps.billing.models import Invoice
from apps.core.models import SiteConfiguration
from apps.people.tests.factories import make_student

pytestmark = pytest.mark.django_db

URL = "/api/config/"


def test_load_is_a_singleton_defaulting_to_cad():
    a = SiteConfiguration.load()
    assert a.currency == "CAD" and a.collects_fees is True
    assert SiteConfiguration.load().pk == a.pk
    assert SiteConfiguration.objects.count() == 1


def test_get_is_open_to_any_authenticated_user(auth_client, staff, parent, api):
    assert auth_client(staff).get(URL).data["currency"] == "CAD"
    assert auth_client(parent).get(URL).status_code == 200
    assert api.get(URL).status_code in (401, 403)


def test_patch_is_superadmin_only(auth_client, superadmin, admin_user):
    assert auth_client(admin_user).patch(URL, {"currency": "USD"}, format="json").status_code == 403
    r = auth_client(superadmin).patch(
        URL, {"country": "bs", "currency": "bsd", "locale": "en-BS"}, format="json"
    )
    assert r.status_code == 200
    assert r.data["currency"] == "BSD" and r.data["country"] == "BS"
    assert SiteConfiguration.load().currency == "BSD"


def test_currency_locks_once_an_invoice_exists(auth_client, superadmin):
    Invoice.objects.create(student=make_student())
    r = auth_client(superadmin).patch(URL, {"currency": "USD"}, format="json")
    assert r.status_code == 400 and "currency" in r.data


def test_new_invoice_takes_the_site_currency():
    SiteConfiguration.load().__class__.objects.update(currency="ZAR")
    inv = Invoice.objects.create(student=make_student())
    assert inv.currency == "ZAR"


def test_cannot_turn_fees_off_with_an_issued_unpaid_invoice(auth_client, superadmin):
    Invoice.objects.create(student=make_student(), status=Invoice.Status.ISSUED)
    r = auth_client(superadmin).patch(URL, {"collects_fees": False}, format="json")
    assert r.status_code == 400


def test_billing_area_is_closed_when_fees_are_off(auth_client, front_desk):
    SiteConfiguration.load().__class__.objects.update(collects_fees=False)
    c = auth_client(front_desk)
    assert c.get("/api/invoices/").status_code == 403
    assert c.get("/api/fee-schedules/").status_code == 403
    assert c.get("/api/credits/").status_code == 403


def test_set_site_config_command_and_force():
    call_command("set_site_config", "--country", "ZW", "--currency", "USD",
                 "--collects-fees", "yes")
    cfg = SiteConfiguration.load()
    assert (cfg.country, cfg.currency, cfg.collects_fees) == ("ZW", "USD", True)

    Invoice.objects.create(student=make_student())
    with pytest.raises(Exception):  # noqa: B017 - CommandError
        call_command("set_site_config", "--currency", "ZWL")
    call_command("set_site_config", "--currency", "ZWL", "--force")
    assert SiteConfiguration.load().currency == "ZWL"
