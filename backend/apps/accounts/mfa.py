"""
TOTP MFA helpers (django-otp).

Staff roles must enrol one TOTP device and clear the second factor each
session before any sensitive endpoint will answer them
(``apps.core.permissions.MFAVerified``). Parents/students may enrol optionally.

Flow:
    1. POST /api/auth/mfa/setup/    -> creates an *unconfirmed* device, returns
       the otpauth:// URI + a PNG-data-URI QR + the base32 secret.
    2. POST /api/auth/mfa/confirm/  -> verifies a code, marks the device
       confirmed, and OTP-verifies the current session.
    3. subsequent logins ask for `otp` and verify against confirmed devices.
"""
from __future__ import annotations

import base64
import io

import qrcode
import qrcode.image.svg
from django_otp import match_token
from django_otp.plugins.otp_totp.models import TOTPDevice

DEVICE_NAME = "default"


def confirmed_totp_devices(user):
    return TOTPDevice.objects.filter(user=user, confirmed=True)


def has_confirmed_totp(user) -> bool:
    return confirmed_totp_devices(user).exists()


def get_or_create_unconfirmed_device(user) -> TOTPDevice:
    """One pending device per user — re-issuing setup rotates the secret."""
    TOTPDevice.objects.filter(user=user, confirmed=False).delete()
    return TOTPDevice.objects.create(user=user, name=DEVICE_NAME, confirmed=False)


def provisioning_uri(device: TOTPDevice) -> str:
    return device.config_url


def qr_data_uri(text: str) -> str:
    """An SVG QR as a data URI — no Pillow dependency in the bundle, and it
    scales cleanly in the enrolment UI."""
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def base32_secret(device: TOTPDevice) -> str:
    return base64.b32encode(device.bin_key).decode("ascii")


def confirm_device(user, token: str) -> TOTPDevice | None:
    """Verify `token` against the user's pending device; on success mark it
    confirmed and return it. Returns None on a bad code."""
    device = TOTPDevice.objects.filter(user=user, confirmed=False).order_by("-id").first()
    if device is None:
        return None
    if device.verify_token(token):
        device.confirmed = True
        device.save(update_fields=["confirmed"])
        return device
    return None


def verify_login_token(user, token: str) -> TOTPDevice | None:
    """Match `token` against any confirmed device (django-otp handles drift and
    per-device throttling). Returns the matched device or None."""
    if not token:
        return None
    return match_token(user, token)
