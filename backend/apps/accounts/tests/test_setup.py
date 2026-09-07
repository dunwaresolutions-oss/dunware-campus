"""First-run setup: the browser creates the initial SUPERADMIN."""
from __future__ import annotations

import pytest

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction, AuditEntry

pytestmark = pytest.mark.django_db

STRONG = "Str0ng-Local-Passphrase!"


def _create(api, **over):
    body = {"username": "founder", "email": "founder@example.test", "password": STRONG}
    body.update(over)
    return api.post("/api/auth/setup/admin/", body, format="json")


def test_status_true_on_a_fresh_install(api):
    r = api.get("/api/auth/setup/status/")
    assert r.status_code == 200
    assert r.data == {"needs_setup": True}


def test_status_false_once_a_superadmin_exists(api, superadmin):
    r = api.get("/api/auth/setup/status/")
    assert r.data == {"needs_setup": False}


def test_creates_the_superadmin_and_signs_the_session_in(api):
    r = _create(api)
    assert r.status_code == 201
    assert r.data["role"] == "SUPERADMIN"
    assert r.data["mfa_enrollment_required"] is True   # routed to MFA next

    u = User.objects.get(username="founder")
    assert u.is_superuser and u.role == Role.SUPERADMIN and u.check_password(STRONG)
    assert AuditEntry.objects.filter(
        action=AuditAction.CREATE, object_type="accounts.User"
    ).exists()

    # the session that created it is now authenticated
    assert api.get("/api/auth/whoami/").status_code == 200
    # and setup is done
    assert api.get("/api/auth/setup/status/").data == {"needs_setup": False}


def test_second_call_is_409(api, superadmin):
    r = _create(api, username="second", email="second@example.test")
    assert r.status_code == 409
    assert User.objects.filter(username="second").count() == 0


def test_weak_password_is_rejected(api):
    r = _create(api, password="password")   # too common / too short
    assert r.status_code == 400
    assert "password" in r.data
    assert not User.objects.filter(is_superuser=True).exists()


def test_bad_email_is_rejected(api):
    r = _create(api, email="not-an-email")
    assert r.status_code == 400
    assert "email" in r.data
