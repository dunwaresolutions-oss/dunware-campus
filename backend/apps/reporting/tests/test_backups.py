"""BackupRun — the record_backup command, the read-only API, the metric."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.reporting.metrics import build_metrics
from apps.reporting.models import BackupRun

pytestmark = pytest.mark.django_db

URL = "/api/backups/"


def _run(**kw):
    kw.setdefault("kind", BackupRun.Kind.SCHEDULED)
    kw.setdefault("status", BackupRun.Status.SUCCESS)
    kw.setdefault("started_at", timezone.now())
    return BackupRun.objects.create(**kw)


def test_record_backup_command_creates_a_row(capsys):
    call_command(
        "record_backup", "--status", "SUCCESS", "--archive", "campus-x.zip.gpg",
        "--size", "12345", "--database-ok", "--media-ok", "--retained", "7",
    )
    run = BackupRun.objects.get()
    assert run.status == "SUCCESS"
    assert run.database_ok and run.media_ok
    assert run.size_bytes == 12345
    assert run.archives_retained == 7
    assert run.finished_at is not None
    # the id is printed for the caller
    assert str(run.pk) in capsys.readouterr().out


def test_record_backup_updates_a_prior_running_row():
    call_command("record_backup", "--status", "RUNNING")
    rid = BackupRun.objects.get().pk
    call_command(
        "record_backup", "--run-id", str(rid), "--status", "SUCCESS",
        "--archive", "campus-y.zip.gpg",
    )
    assert BackupRun.objects.count() == 1
    run = BackupRun.objects.get()
    assert run.status == "SUCCESS" and run.archive_name == "campus-y.zip.gpg"


def test_record_backup_prunes_old_rows():
    for _ in range(5):
        _run()
    call_command("record_backup", "--status", "SUCCESS", "--keep", "3")
    assert BackupRun.objects.count() == 3


def test_api_is_superadmin_only(auth_client, superadmin, admin_user, staff):
    _run(archive_name="a.gpg")
    assert auth_client(superadmin).get(URL).data["count"] == 1
    assert auth_client(admin_user).get(URL).status_code == 403
    assert auth_client(staff).get(URL).status_code == 403


def test_metric_reflects_history(superadmin):
    _run(started_at=timezone.now() - dt.timedelta(hours=2), size_bytes=999)
    _run(
        status=BackupRun.Status.FAILED, error="pg_dump exited 1",
        started_at=timezone.now() - dt.timedelta(days=1),
    )
    _run(kind=BackupRun.Kind.VERIFY)

    b = build_metrics(superadmin)["system"]["backup"]
    assert b["configured"] is True
    assert b["stale"] is False           # a success under 48h old
    assert b["last_success_bytes"] == 999
    assert b["failures_7d"] == 1
    assert b["last_verified_at"] is not None
