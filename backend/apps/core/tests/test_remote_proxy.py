"""RemoteClientIPMiddleware — restore the real client IP, but only from loopback."""
from __future__ import annotations

from django.test import RequestFactory, override_settings

from apps.core.remote_proxy import RemoteClientIPMiddleware

_rf = RequestFactory()


def _run(**meta):
    request = _rf.get("/api/whoami/")
    request.META.update(meta)
    RemoteClientIPMiddleware(lambda r: None).process_request(request)
    return request


def test_inert_when_remote_access_disabled():
    req = _run(REMOTE_ADDR="127.0.0.1", HTTP_CF_CONNECTING_IP="203.0.113.9")
    assert req.META["REMOTE_ADDR"] == "127.0.0.1"


@override_settings(
    REMOTE_ACCESS_ENABLED=True, REMOTE_ACCESS_CLIENT_IP_HEADER="CF-Connecting-IP"
)
def test_restores_real_ip_from_loopback_peer():
    req = _run(REMOTE_ADDR="127.0.0.1", HTTP_CF_CONNECTING_IP="203.0.113.9")
    assert req.META["REMOTE_ADDR"] == "203.0.113.9"
    assert req.META["HTTP_X_FORWARDED_FOR"] == "203.0.113.9"


@override_settings(
    REMOTE_ACCESS_ENABLED=True, REMOTE_ACCESS_CLIENT_IP_HEADER="CF-Connecting-IP"
)
def test_lan_peer_cannot_forge_the_header():
    # A box on the LAN talking straight to Django is not loopback -> ignored.
    req = _run(REMOTE_ADDR="192.168.1.50", HTTP_CF_CONNECTING_IP="203.0.113.9")
    assert req.META["REMOTE_ADDR"] == "192.168.1.50"


@override_settings(REMOTE_ACCESS_ENABLED=True, REMOTE_ACCESS_CLIENT_IP_HEADER="")
def test_blank_header_setting_is_inert():
    req = _run(REMOTE_ADDR="127.0.0.1", HTTP_CF_CONNECTING_IP="203.0.113.9")
    assert req.META["REMOTE_ADDR"] == "127.0.0.1"


@override_settings(
    REMOTE_ACCESS_ENABLED=True, REMOTE_ACCESS_CLIENT_IP_HEADER="CF-Connecting-IP"
)
def test_garbage_header_value_is_ignored():
    req = _run(REMOTE_ADDR="127.0.0.1", HTTP_CF_CONNECTING_IP="not-an-ip")
    assert req.META["REMOTE_ADDR"] == "127.0.0.1"


@override_settings(
    REMOTE_ACCESS_ENABLED=True, REMOTE_ACCESS_CLIENT_IP_HEADER="X-Forwarded-For"
)
def test_takes_first_entry_of_a_forwarded_list():
    req = _run(
        REMOTE_ADDR="::1",
        HTTP_X_FORWARDED_FOR="198.51.100.7, 70.0.0.1, 127.0.0.1",
    )
    assert req.META["REMOTE_ADDR"] == "198.51.100.7"


def test_defaults_are_off():
    from django.conf import settings

    assert settings.REMOTE_ACCESS_ENABLED is False
    assert settings.REMOTE_ACCESS_HOSTS == []
    assert settings.REMOTE_ACCESS_CLIENT_IP_HEADER == ""
