"""Read-only operational surfaces for the console."""
from __future__ import annotations

import os
import subprocess
import sys

from django.conf import settings
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.hotfix import active_hotfixes
from apps.core.models import SchoolProfile
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
    or superadmin, MFA-verified. Accepts multipart (for the logo) or JSON.
    """

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated(), StaffOnly(), MFAVerified()]
        return [IsAuthenticated(), AdminOnly(), MFAVerified()]

    def get(self, request):
        profile = SchoolProfile.load()
        return Response(SchoolProfileSerializer(profile, context={"request": request}).data)

    def patch(self, request):
        profile = SchoolProfile.load()
        ser = SchoolProfileSerializer(
            profile, data=request.data, partial=True, context={"request": request}
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
