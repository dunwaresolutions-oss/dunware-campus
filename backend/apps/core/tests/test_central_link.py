"""Campus Central link (C1): deployment_mode guard against HEADQUARTERS,
and the link_central / unlink_central / central_link_test management
commands. See docs/CENTRAL_SYNC_SCOPE.md for the C0 decisions this builds on.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command

from apps.core.models import SiteConfiguration

pytestmark = pytest.mark.django_db

CONFIG_URL = "/api/config/"
A_SCHOOL_ID = str(uuid.uuid4())


def test_campus_itself_can_never_be_set_to_headquarters_at_the_model_level():
    cfg = SiteConfiguration.load()
    cfg.deployment_mode = SiteConfiguration.DeploymentMode.HEADQUARTERS
    with pytest.raises(ValidationError):
        cfg.save()


def test_patch_rejects_headquarters(auth_client, superadmin):
    r = auth_client(superadmin).patch(
        CONFIG_URL, {"deployment_mode": "HEADQUARTERS"}, format="json"
    )
    assert r.status_code == 400
    assert "deployment_mode" in r.data


def test_set_site_config_rejects_headquarters():
    with pytest.raises(Exception):  # noqa: B017 - CommandError
        call_command("set_site_config", "--deployment-mode", "HEADQUARTERS")
    assert SiteConfiguration.load().deployment_mode == "SINGLE"


def test_link_central_requires_school_mode_first():
    with pytest.raises(Exception):  # noqa: B017 - CommandError
        call_command(
            "link_central", "--central-url", "https://hq.example.gov.bs",
            "--school-id", A_SCHOOL_ID, "--token", "sch_abc123",
        )


def test_link_central_sets_the_link_fields_and_enables_sync():
    call_command("set_site_config", "--deployment-mode", "SCHOOL")
    call_command(
        "link_central", "--central-url", "https://hq.example.gov.bs",
        "--school-id", A_SCHOOL_ID, "--token", "sch_abc123", "--sync-interval-minutes", "60",
    )
    cfg = SiteConfiguration.load()
    assert str(cfg.school_id) == A_SCHOOL_ID
    assert cfg.central_url == "https://hq.example.gov.bs"
    assert cfg.central_token == "sch_abc123"  # decrypts transparently on read
    assert cfg.sync_enabled is True
    assert cfg.sync_interval_minutes == 60


def test_link_central_rejects_a_non_uuid_school_id():
    call_command("set_site_config", "--deployment-mode", "SCHOOL")
    with pytest.raises(Exception):  # noqa: B017 - CommandError
        call_command(
            "link_central", "--central-url", "https://hq.example.gov.bs",
            "--school-id", "not-a-uuid", "--token", "sch_abc123",
        )


def test_central_token_is_encrypted_at_rest():
    from django.db import connection

    call_command("set_site_config", "--deployment-mode", "SCHOOL")
    call_command(
        "link_central", "--central-url", "https://hq.example.gov.bs",
        "--school-id", A_SCHOOL_ID, "--token", "sch_abc123",
    )
    # bypass the ORM's field conversion entirely -- this is what's actually on disk
    with connection.cursor() as cur:
        cur.execute("SELECT central_token FROM core_site_configuration LIMIT 1")
        stored = cur.fetchone()[0]
    assert stored != "sch_abc123"
    assert stored.startswith("cg1:")


def test_unlink_central_clears_everything():
    call_command("set_site_config", "--deployment-mode", "SCHOOL")
    call_command(
        "link_central", "--central-url", "https://hq.example.gov.bs",
        "--school-id", A_SCHOOL_ID, "--token", "sch_abc123",
    )
    call_command("unlink_central")
    cfg = SiteConfiguration.load()
    assert cfg.school_id is None
    assert cfg.central_url == ""
    assert cfg.central_token == ""
    assert cfg.sync_enabled is False
    # deployment_mode is untouched by unlink -- still organisationally a school
    assert cfg.deployment_mode == "SCHOOL"


def test_central_link_test_with_no_url_anywhere_refuses():
    with pytest.raises(Exception):  # noqa: B017 - CommandError
        call_command("central_link_test")


def test_central_link_test_reports_reachable(monkeypatch):
    class FakeResponse:
        status_code = 200

    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse())
    call_command("central_link_test", "--central-url", "https://hq.example.gov.bs")


def test_central_link_test_reports_404_as_not_central_yet(monkeypatch):
    class FakeResponse:
        status_code = 404

    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse())
    with pytest.raises(Exception):  # noqa: B017 - CommandError
        call_command("central_link_test", "--central-url", "https://hq.example.gov.bs")


def test_central_link_test_reports_a_network_failure(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", boom)
    with pytest.raises(Exception):  # noqa: B017 - CommandError
        call_command("central_link_test", "--central-url", "https://hq.example.gov.bs")
