"""
Stashes the current actor and source IP in a context var so model signal
handlers and the ``record()`` helper can attribute an audit entry without
threading ``request`` through every call.
"""
from __future__ import annotations

import contextvars

_actor = contextvars.ContextVar("campus_audit_actor", default=None)
_ip = contextvars.ContextVar("campus_audit_ip", default=None)


def current_actor():
    return _actor.get()


def current_ip():
    return _ip.get()


def _client_ip(request) -> str | None:
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def axes_client_ip(request, _default=None) -> str | None:
    """`settings.AXES_CLIENT_IP_CALLABLE` — keep axes and the audit log agreeing
    on which address a request came from (both trust Caddy's X-Forwarded-For)."""
    return _client_ip(request)


class AuditContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        actor_token = _actor.set(user if (user and user.is_authenticated) else None)
        ip_token = _ip.set(_client_ip(request))
        try:
            return self.get_response(request)
        finally:
            _actor.reset(actor_token)
            _ip.reset(ip_token)
