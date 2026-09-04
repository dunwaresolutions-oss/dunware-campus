"""
``settings.AXES_LOCKOUT_CALLABLE`` — the response django-axes returns once an
account / IP is locked out. Plain 429 JSON (no account enumeration) plus a
LOCKOUT entry in the audit log.
"""
from __future__ import annotations

from django.http import JsonResponse

from apps.audit.models import AuditAction
from apps.audit.services import record_safe


def lockout_response(request, credentials=None):
    username = ""
    if credentials:
        username = credentials.get("username", "") or credentials.get("email", "")
    record_safe(
        AuditAction.LOCKOUT,
        summary=f"login lockout for {username or 'unknown'}"[:255],
        extra={"path": getattr(request, "path", "")},
    )
    return JsonResponse(
        {"detail": "Too many failed sign-in attempts. Try again later."},
        status=429,
    )
