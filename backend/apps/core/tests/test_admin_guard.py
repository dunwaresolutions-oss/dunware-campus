"""Break-glass guard on /admin/ (superuser + allow-listed IP + MFA)."""
from __future__ import annotations

import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db

# Rendering /admin/login/ touches {% static %}; use non-manifest storage so the
# test passes whether or not collectstatic has run (CI uses the dev settings).
_PLAIN_STATIC = override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)


def test_anonymous_admin_is_404_not_302(client):
    # 404, not a login redirect — the admin does not advertise itself.
    assert client.get("/admin/").status_code == 404


@_PLAIN_STATIC
def test_login_page_reachable_from_allowlisted_ip(client):
    assert client.get("/admin/login/").status_code == 200


@override_settings(CAMPUS_ADMIN_IP_ALLOWLIST=["10.9.9.9"])
def test_blocked_from_non_allowlisted_ip(client):
    assert client.get("/admin/login/").status_code == 404


def test_superuser_without_mfa_is_still_blocked(client, superadmin):
    client.force_login(superadmin)
    assert client.get("/admin/").status_code == 404


def test_non_superuser_staff_blocked(client, make_user):
    from apps.accounts.models import Role

    admin_role = make_user(username="dir", role=Role.ADMIN)
    client.force_login(admin_role)
    assert client.get("/admin/").status_code == 404
