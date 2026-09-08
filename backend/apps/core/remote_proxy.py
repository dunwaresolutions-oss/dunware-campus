"""
Real-client-IP restoration for optional off-premises remote access.

When ``settings.REMOTE_ACCESS_ENABLED`` is on, an off-site request reaches Django
from the **loopback address of this box** — a tunnel client (cloudflared), a VPN
endpoint, or the bundled Caddy forwarded it locally. The true client address is
carried in a header the fronting layer set:

    Cloudflare Tunnel  ->  CF-Connecting-IP   (a single, authoritative address)
    WireGuard / VPN    ->  "" (the packet already has the real source)
    plain gateway      ->  X-Forwarded-For    (first entry)

This middleware copies that header into ``REMOTE_ADDR`` (and normalises
``X-Forwarded-For`` to the same single value so the audit middleware's
``_client_ip`` agrees) **only when the immediate peer is a trusted local
proxy**. That last condition is the whole security story: a machine on the LAN
that talks to Django directly is not loopback, so it can never forge the header
and poison django-axes lockout or the audit log.

Completely inert unless ``REMOTE_ACCESS_ENABLED`` is true *and*
``REMOTE_ACCESS_CLIENT_IP_HEADER`` is non-empty — i.e. nothing happens on a
normal LAN-only install.
"""
from __future__ import annotations

import ipaddress

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin


def _meta_key(header_name: str) -> str:
    """"CF-Connecting-IP" -> "HTTP_CF_CONNECTING_IP" (the WSGI/`request.META` key)."""
    return "HTTP_" + header_name.strip().upper().replace("-", "_")


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


class RemoteClientIPMiddleware(MiddlewareMixin):
    """Restore the real client IP from a fronting proxy's header — safely."""

    def process_request(self, request):
        if not getattr(settings, "REMOTE_ACCESS_ENABLED", False):
            return None

        header_name = getattr(settings, "REMOTE_ACCESS_CLIENT_IP_HEADER", "") or ""
        if not header_name:
            return None

        peer = request.META.get("REMOTE_ADDR", "")
        trusted = getattr(
            settings, "REMOTE_ACCESS_TRUSTED_PROXIES", ["127.0.0.1", "::1"]
        )
        if peer not in trusted:
            # The request did not come through our local front door — do not
            # let it dictate its own source address.
            return None

        claimed = request.META.get(_meta_key(header_name), "")
        claimed = claimed.split(",")[0].strip()
        if not claimed or not _is_ip(claimed):
            return None

        request.META["REMOTE_ADDR"] = claimed
        # Keep the two IP readers (this, and apps.audit.middleware._client_ip,
        # which prefers X-Forwarded-For) pointing at the same trusted value.
        request.META["HTTP_X_FORWARDED_FOR"] = claimed
        return None
