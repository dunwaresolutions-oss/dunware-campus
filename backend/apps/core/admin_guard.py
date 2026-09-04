"""
Break-glass guard for the Django admin (see docs/PII_SECURITY.md §2).

The admin is an emergency console, not an operational surface. Three gates,
all required, before any ``/admin/`` view runs:

1. authenticated **superuser** (role-based staff do not qualify);
2. request IP in ``settings.CAMPUS_ADMIN_IP_ALLOWLIST``;
3. the session is **OTP-verified** (``settings.CAMPUS_ADMIN_REQUIRE_MFA``).

A failure is audited and returns 404 — the admin should not even advertise its
presence to a client that has no business there. The login page itself is
exempt from gates 1 and 3 (you have to be able to reach it to log in) but not
from the IP allow-list.
"""
from __future__ import annotations

from django.conf import settings
from django.http import Http404
from django.utils.deprecation import MiddlewareMixin

from apps.audit.middleware import current_ip
from apps.audit.models import AuditAction
from apps.audit.services import record_safe


def _admin_prefix() -> str:
    return "/admin/"


class AdminBreakGlassMiddleware(MiddlewareMixin):
    def process_request(self, request):
        path = request.path
        if not path.startswith(_admin_prefix()):
            return None

        ip = current_ip() or request.META.get("REMOTE_ADDR")
        allow = list(getattr(settings, "CAMPUS_ADMIN_IP_ALLOWLIST", ["127.0.0.1"]))

        if allow and ip not in allow:
            self._deny(request, f"admin blocked: IP {ip} not allow-listed")
            raise Http404

        # The login endpoints must stay reachable for an un-authed superuser.
        is_login = path.rstrip("/").endswith("/login") or path.startswith("/admin/login")
        if is_login:
            return None

        user = getattr(request, "user", None)
        if not (user and user.is_authenticated and user.is_superuser):
            self._deny(request, "admin blocked: not a superuser")
            raise Http404

        if getattr(settings, "CAMPUS_ADMIN_REQUIRE_MFA", True):
            is_verified = getattr(user, "is_verified", None)
            if not (callable(is_verified) and is_verified()):
                self._deny(request, "admin blocked: session not MFA-verified")
                raise Http404

        return None

    @staticmethod
    def _deny(request, reason: str) -> None:
        record_safe(
            AuditAction.PERMISSION_DENIED,
            summary=f"{request.method} {request.path} — {reason}"[:255],
            extra={"reason": "admin_break_glass"},
        )
