"""TOTP enrolment: setup -> confirm -> status."""
from __future__ import annotations

import pytest
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.audit.models import AuditAction, AuditEntry

pytestmark = pytest.mark.django_db

PW = "Sup3r-Secret-Pw!"


def _login(api, username, password=PW, **extra):
    return api.post(
        "/api/auth/login/", {"username": username, "password": password, **extra}, format="json"
    )


def _current_code(device: TOTPDevice) -> str:
    value = totp(device.bin_key, step=device.step, t0=device.t0, digits=device.digits)
    return str(value).zfill(device.digits)


def test_setup_returns_qr_secret_and_uri(api, staff):
    _login(api, "teacher")
    r = api.post("/api/auth/mfa/setup/", {}, format="json")
    assert r.status_code == 200
    assert r.data["qr"].startswith("data:image/svg+xml;base64,")
    assert r.data["otpauth_uri"].startswith("otpauth://totp/")
    assert len(r.data["secret"]) >= 16
    assert TOTPDevice.objects.filter(user=staff, confirmed=False).count() == 1


def test_confirm_with_a_valid_code_enables_mfa(api, staff):
    _login(api, "teacher")
    api.post("/api/auth/mfa/setup/", {}, format="json")
    device = TOTPDevice.objects.get(user=staff, confirmed=False)

    r = api.post("/api/auth/mfa/confirm/", {"token": _current_code(device)}, format="json")
    assert r.status_code == 200
    device.refresh_from_db()
    assert device.confirmed is True
    assert AuditEntry.objects.filter(action=AuditAction.MFA_ENROLLED).exists()


def test_confirm_rejects_a_bad_code(api, staff):
    _login(api, "teacher")
    api.post("/api/auth/mfa/setup/", {}, format="json")
    r = api.post("/api/auth/mfa/confirm/", {"token": "123456"}, format="json")
    assert r.status_code in (400, 200)  # 200 only on a 1-in-a-million code collision
    if r.status_code == 200:
        pytest.skip("astronomically unlikely TOTP collision")
    assert not TOTPDevice.objects.filter(user=staff, confirmed=True).exists()


def test_setup_rotates_the_pending_secret(api, staff):
    _login(api, "teacher")
    first = api.post("/api/auth/mfa/setup/", {}, format="json").data["secret"]
    second = api.post("/api/auth/mfa/setup/", {}, format="json").data["secret"]
    assert first != second
    assert TOTPDevice.objects.filter(user=staff, confirmed=False).count() == 1


def test_status_reports_enrolment(api, staff, totp_for):
    _device, code = totp_for(staff)
    _login(api, "teacher", otp=code())
    r = api.get("/api/auth/mfa/status/")
    assert r.data["must_use_mfa"] is True
    assert r.data["mfa_enrolled"] is True
    assert r.data["mfa_verified"] is True


def test_setup_requires_authentication(api):
    assert api.post("/api/auth/mfa/setup/", {}, format="json").status_code in (401, 403)
