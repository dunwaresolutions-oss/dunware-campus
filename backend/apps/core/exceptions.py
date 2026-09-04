"""
DRF exception handler that records every access denial to the audit log.

A 401/403 on a sensitive endpoint is a security-relevant event: it means
someone reached for data they could not have. We log the *fact* (actor, path,
reason) — never the payload — and let DRF build the response as normal.
"""
from __future__ import annotations

from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.views import exception_handler as drf_exception_handler

from apps.audit.models import AuditAction
from apps.audit.services import record_safe


def audited_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if isinstance(exc, (PermissionDenied, NotAuthenticated)):
        request = context.get("request")
        view = context.get("view")
        path = getattr(request, "path", "")
        view_name = view.__class__.__name__ if view is not None else ""
        record_safe(
            AuditAction.PERMISSION_DENIED,
            summary=f"{getattr(request, 'method', '?')} {path} denied ({view_name})"[:255],
            extra={"reason": exc.__class__.__name__},
        )

    return response
