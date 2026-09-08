"""GET /api/remote-access/status/ — superadmin-only, read-only."""
from __future__ import annotations

import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db

URL = "/api/remote-access/status/"


def test_superadmin_sees_status(auth_client, superadmin):
    resp = auth_client(superadmin).get(URL)
    assert resp.status_code == 200
    body = resp.data
    assert body["enabled"] is False
    assert body["mode"] == "off"
    assert body["hosts"] == []
    assert "manage_hint" in body
    assert body["hotfixes"] == []


def test_admin_is_denied(auth_client, admin_user):
    assert auth_client(admin_user).get(URL).status_code == 403


def test_front_desk_is_denied(auth_client, front_desk):
    assert auth_client(front_desk).get(URL).status_code == 403


def test_anonymous_is_denied(api):
    assert api.get(URL).status_code in (401, 403)


@override_settings(
    REMOTE_ACCESS_ENABLED=True,
    REMOTE_ACCESS_HOSTS=["portal.school.edu.bs"],
    REMOTE_ACCESS_CLIENT_IP_HEADER="CF-Connecting-IP",
)
def test_mode_is_inferred_from_settings(auth_client, superadmin):
    body = auth_client(superadmin).get(URL).data
    assert body["enabled"] is True
    assert body["mode"] == "Cloudflare Tunnel"
    assert body["hosts"] == ["portal.school.edu.bs"]
