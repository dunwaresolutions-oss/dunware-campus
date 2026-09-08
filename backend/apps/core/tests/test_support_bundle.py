"""support_bundle — produces one redacted ZIP, safe to carry off-site."""
from __future__ import annotations

import zipfile

import pytest
from django.core.management import call_command

from apps.core.management.commands.support_bundle import _redact_env

pytestmark = pytest.mark.django_db


def test_redact_env_strips_secret_values_and_url_passwords():
    raw = "\n".join(
        [
            "# a comment",
            "DEBUG=False",
            "SECRET_KEY=super-secret-value",
            "FIELD_ENCRYPTION_KEY=AAAABBBBCCCCDDDD",
            "EMAIL_HOST_PASSWORD=hunter2",
            "DATABASE_URL=postgres://campus:s3cr3t@127.0.0.1:5432/campus",
            "ALLOWED_HOSTS=localhost,127.0.0.1",
        ]
    )
    out = _redact_env(raw)
    assert "# a comment" in out
    assert "DEBUG=False" in out
    assert "super-secret-value" not in out
    assert "AAAABBBBCCCCDDDD" not in out
    assert "hunter2" not in out
    assert "s3cr3t" not in out
    assert "postgres://campus:***@127.0.0.1:5432/campus" in out
    assert "ALLOWED_HOSTS=localhost,127.0.0.1" in out


def test_bundle_is_written_and_has_the_expected_shape(tmp_path):
    call_command("support_bundle", "--output", str(tmp_path))
    zips = list(tmp_path.glob("support-bundle-*.zip"))
    assert len(zips) == 1
    with zipfile.ZipFile(zips[0]) as zf:
        names = set(zf.namelist())
        assert "report.txt" in names
        assert "health/db.json" in names
        assert "health/audit.json" in names
        assert "health/check.txt" in names
        report = zf.read("report.txt").decode()
    assert "build" in report
    assert "install_root" in report


def test_explicit_zip_path_is_honoured(tmp_path):
    target = tmp_path / "nested" / "handoff.zip"
    call_command("support_bundle", "--output", str(target))
    assert target.exists()
