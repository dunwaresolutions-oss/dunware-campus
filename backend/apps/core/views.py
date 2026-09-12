"""Read-only operational surfaces for the console."""
from __future__ import annotations

import os
import subprocess
import sys

from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.hotfix import active_hotfixes
from apps.core.models import SchoolProfile, SiteConfiguration
from apps.core.money import COUNTRY_CURRENCIES, CURRENCIES, currency_symbol
from apps.core.permissions import AdminOnly, MFAVerified, StaffOnly, SuperadminOnly
from apps.core.serializers import SchoolProfileSerializer
from apps.core.support import install_root
from apps.core.version import build_stamp

_SC = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "sc.exe")


def _service_state(name: str) -> str:
    if sys.platform != "win32":
        return "unknown"
    try:
        out = subprocess.run(  # noqa: S603 - fixed argv, absolute exe
            [_SC, "query", name], capture_output=True, text=True, timeout=10, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    for token in ("RUNNING", "STOPPED", "START_PENDING", "STOP_PENDING", "PAUSED"):
        if token in out:
            return token
    return "not installed"


def _mode_guess() -> str:
    if not getattr(settings, "REMOTE_ACCESS_ENABLED", False):
        return "off"
    header = (getattr(settings, "REMOTE_ACCESS_CLIENT_IP_HEADER", "") or "").lower()
    remote = install_root() / "remote"
    if header == "cf-connecting-ip" or (remote / "config.yml").exists():
        return "Cloudflare Tunnel"
    if (remote / "wg" / "wg0.conf").exists():
        return "WireGuard VPN"
    if header == "x-forwarded-for":
        return "Gateway (own cert)"
    return "on (unrecognised)"


class SchoolProfileView(APIView):
    """``GET`` / ``PATCH /api/school-profile/`` — the institution's own identity
    (name, address, logo) used on report cards / IEPs and in the console chrome.

    Read: any staff role (the UI shows the name/logo everywhere). Write: admin
    or superadmin, MFA-verified — *except* a signature-only PATCH, which the
    designated principal may send even without an admin role (``patch()``
    then still checks it really is them, or a superadmin). Accepts multipart
    (for the logo/signature) or JSON.
    """

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated(), StaffOnly(), MFAVerified()]
        if self.request.method == "PATCH" and _is_signature_only_patch(self.request.data):
            return [IsAuthenticated(), StaffOnly(), MFAVerified()]
        return [IsAuthenticated(), AdminOnly(), MFAVerified()]

    def get(self, request):
        profile = SchoolProfile.load()
        return Response(SchoolProfileSerializer(profile, context={"request": request}).data)

    def patch(self, request):
        profile = SchoolProfile.load()
        data = request.data
        # Designating who "is" the principal is a trust decision — superadmin
        # only. Placing the signature image is further restricted to that one
        # account (or a superadmin), enforced again on SchoolSignatureView.
        if "principal_user" in data and getattr(request.user, "role", None) != "SUPERADMIN":
            raise PermissionDenied("Only a superadmin may designate the principal.")
        if _has_signature_payload(data) and not _may_sign(request.user, profile):
            raise PermissionDenied(
                "Only the designated principal may upload or replace the signature."
            )
        ser = SchoolProfileSerializer(
            profile, data=data, partial=True, context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    def delete(self, request):
        """Clear the logo only (keeps the text fields)."""
        profile = SchoolProfile.load()
        if profile.logo:
            profile.logo.delete(save=False)
            profile.logo = None
            profile.save(update_fields=["logo", "updated_at"])
        return Response(SchoolProfileSerializer(profile, context={"request": request}).data)


def _has_signature_payload(data) -> bool:
    try:
        return "signature" in data
    except TypeError:  # pragma: no cover - defensive
        return False


def _is_signature_only_patch(data) -> bool:
    try:
        keys = set(data.keys())
    except AttributeError:  # pragma: no cover - defensive
        return False
    return keys == {"signature"}


def _may_sign(user, profile: SchoolProfile) -> bool:
    if getattr(user, "role", None) == "SUPERADMIN":
        return True
    return bool(profile.principal_user_id) and str(profile.principal_user_id) == str(user.pk)


class SchoolSignatureView(APIView):
    """``GET`` streams the decrypted signature image (any staff); ``DELETE``
    clears it — restricted, like the upload, to the designated principal or a
    superadmin. There is no direct upload endpoint here: the image is set via
    ``PATCH /api/school-profile/`` (multipart), which carries the same check.
    """

    permission_classes = [IsAuthenticated, StaffOnly, MFAVerified]

    def get(self, request):
        profile = SchoolProfile.load()
        if not profile.signature:
            raise Http404
        fh = profile.signature.open("rb")  # EncryptedFileSystemStorage decrypts here
        return FileResponse(fh, content_type="image/*")

    def delete(self, request):
        profile = SchoolProfile.load()
        if not _may_sign(request.user, profile):
            raise PermissionDenied(
                "Only the designated principal may remove the signature."
            )
        if profile.signature:
            profile.signature.delete(save=False)
            profile.signature = None
            profile.save(update_fields=["signature", "updated_at"])
        return Response(status=204)


class SchoolLogoView(APIView):
    """``GET`` streams the school logo. Unlike the signature, the logo lives on
    plain (unencrypted) storage — it's public branding, not PII — but it still
    needs a real view: ``logo.url`` resolves to a bare ``/media/...`` path, and
    nothing serves that in production (``DEBUG=False`` means Django's own
    ``static()`` media helper never runs, and Caddy reverse-proxies ``/media/*``
    to Django rather than serving files itself — see ``docs/DEPLOYMENT.md``).
    Clearing the logo is already handled by ``DELETE /api/school-profile/``.
    """

    permission_classes = [IsAuthenticated, StaffOnly, MFAVerified]

    def get(self, request):
        profile = SchoolProfile.load()
        if not profile.logo:
            raise Http404
        fh = profile.logo.open("rb")
        return FileResponse(fh, content_type="image/*")


def _currency_locked() -> bool:
    from apps.billing.models import Invoice

    return Invoice.objects.exists()


class SiteConfigView(APIView):
    """``GET`` / ``PATCH /api/config/`` — per-install region & fiscal settings.

    GET: any authenticated user (the SPA needs currency + collects_fees to
    render). PATCH: superadmin + MFA, and only before it locks — ``currency``
    is frozen once any invoice exists; ``collects_fees`` can't be turned off
    while an issued unpaid invoice exists. The companion tool does the same
    via ``manage set_site_config``.
    """

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]
        return [IsAuthenticated(), SuperadminOnly(), MFAVerified()]

    def _payload(self, cfg):
        return {
            "country": cfg.country,
            "currency": cfg.currency,
            "currency_symbol": currency_symbol(cfg.currency),
            "locale": cfg.locale,
            "collects_fees": cfg.collects_fees,
            "deployment_mode": cfg.deployment_mode,
            "currency_locked": _currency_locked(),
            "currency_options": [
                {"code": c, "symbol": s, "name": n} for c, (s, n) in CURRENCIES.items()
            ],
            "country_currencies": COUNTRY_CURRENCIES,
        }

    def get(self, request):
        return Response(self._payload(SiteConfiguration.load()))

    def patch(self, request):
        from rest_framework.exceptions import ValidationError

        from apps.billing.models import Invoice

        cfg = SiteConfiguration.load()
        data = request.data
        if "currency" in data and data["currency"] != cfg.currency and _currency_locked():
            raise ValidationError(
                {"currency": "Locked — invoices already exist in the current currency."}
            )
        if data.get("collects_fees") is False and cfg.collects_fees:
            open_unpaid = Invoice.objects.filter(
                status__in=[Invoice.Status.ISSUED, Invoice.Status.PARTIALLY_PAID,
                            Invoice.Status.OVERDUE]
            ).exists()
            if open_unpaid:
                raise ValidationError({
                    "collects_fees":
                        "There are issued, unpaid invoices — settle or void them first.",
                })
        for field in ("country", "currency", "locale", "collects_fees", "deployment_mode"):
            if field in data:
                setattr(cfg, field, data[field])
        cfg.currency = (cfg.currency or "CAD").upper()[:3]
        cfg.country = (cfg.country or "").upper()[:2]
        cfg.save()
        return Response(self._payload(cfg))


class RemoteAccessStatusView(APIView):
    """``GET /api/remote-access/status/`` — what off-premises access is configured.

    Read-only on purpose: provisioning and teardown are done by a technician
    with ``deploy/remote-setup.ps1`` (the app service is unprivileged and cannot
    register Windows services or edit the ACL-locked .env).
    """

    permission_classes = [IsAuthenticated, SuperadminOnly, MFAVerified]

    def get(self, request):
        return Response(
            {
                "enabled": bool(getattr(settings, "REMOTE_ACCESS_ENABLED", False)),
                "mode": _mode_guess(),
                "hosts": list(getattr(settings, "REMOTE_ACCESS_HOSTS", [])),
                "client_ip_header": getattr(settings, "REMOTE_ACCESS_CLIENT_IP_HEADER", ""),
                "service": _service_state("Campus Remote"),
                "hotfixes": active_hotfixes(),
                "build": build_stamp(),
                "manage_hint": (
                    "To change this, open “Campus - Remote Access Setup” "
                    "from the Start menu on the Campus box (it asks for "
                    "administrator rights). The scripted equivalent is "
                    "scripts\\remote-setup.ps1."
                ),
            }
        )
