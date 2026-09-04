"""Login: password, MFA gate, audit trail, lockout."""
from __future__ import annotations

import pytest

from apps.audit.models import AuditAction, AuditEntry

pytestmark = pytest.mark.django_db

PW = "Sup3r-Secret-Pw!"


def _login(api, username, password=PW, **extra):
    return api.post(
        "/api/auth/login/", {"username": username, "password": password, **extra}, format="json"
    )


def test_portal_user_logs_in_without_mfa(api, parent):
    r = _login(api, "parent")
    assert r.status_code == 200
    assert r.data["role"] == "PARENT"
    assert r.data["mfa_enrolled"] is False
    assert r.data["mfa_enrollment_required"] is False
    assert AuditEntry.objects.filter(action=AuditAction.LOGIN).exists()


def test_bad_password_is_401_and_audited(api, parent):
    r = _login(api, "parent", password="nope")
    assert r.status_code == 401
    assert AuditEntry.objects.filter(action=AuditAction.LOGIN_FAILED).exists()


def test_unknown_user_is_401(api):
    assert _login(api, "ghost").status_code == 401


def test_staff_without_a_device_gets_a_limited_session(api, staff):
    r = _login(api, "teacher")
    assert r.status_code == 200
    assert r.data["mfa_enrollment_required"] is True
    assert r.data["mfa_verified"] is False


def test_staff_login_without_a_code_is_refused(api, staff, totp_for):
    totp_for(staff)
    r = _login(api, "teacher")
    assert r.status_code == 401
    assert r.data["mfa_required"] is True


def test_staff_login_with_a_wrong_code_is_refused(api, staff, totp_for):
    totp_for(staff)
    assert _login(api, "teacher", otp="000000").status_code == 401


def test_staff_login_with_a_valid_code_succeeds(api, staff, totp_for):
    _device, code = totp_for(staff)
    ok = _login(api, "teacher", otp=code())
    assert ok.status_code == 200
    assert ok.data["mfa_verified"] is True
    assert AuditEntry.objects.filter(action=AuditAction.MFA_VERIFIED).exists()


def test_lockout_after_repeated_failures(api, parent, settings):
    settings.AXES_ENABLED = True
    from axes.utils import reset

    reset()
    try:
        for _ in range(5):
            _login(api, "parent", password="wrong")
        blocked = _login(api, "parent")  # correct password, but now locked
        assert blocked.status_code == 429
        assert AuditEntry.objects.filter(action=AuditAction.LOCKOUT).exists()
    finally:
        reset()
        settings.AXES_ENABLED = False


def test_logout_clears_the_session(api, parent):
    _login(api, "parent")
    assert api.post("/api/auth/logout/").status_code == 204
    assert api.get("/api/auth/whoami/").status_code in (401, 403)
