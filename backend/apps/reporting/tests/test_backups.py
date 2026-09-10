"""BackupRun — the record_backup command, the read-only API, the metric."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.reporting import backup_runner
from apps.reporting.metrics import build_metrics
from apps.reporting.models import BackupRun

pytestmark = pytest.mark.django_db

URL = "/api/backups/"
RUN_URL = "/api/backups/run/"


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


def test_api_is_admin_and_superadmin_only(auth_client, superadmin, admin_user, staff):
    _run(archive_name="a.gpg")
    assert auth_client(superadmin).get(URL).data["count"] == 1
    assert auth_client(admin_user).get(URL).data["count"] == 1
    assert auth_client(staff).get(URL).status_code == 403


def test_run_action_needs_admin(auth_client, staff):
    assert auth_client(staff).post(RUN_URL, {}, format="json").status_code == 403


def test_run_action_409_while_a_manual_backup_is_running(auth_client, superadmin):
    _run(kind=BackupRun.Kind.MANUAL, status=BackupRun.Status.RUNNING)
    resp = auth_client(superadmin).post(RUN_URL, {}, format="json")
    assert resp.status_code == 409


def test_run_action_launches_and_returns_the_running_row(
    auth_client, admin_user, monkeypatch
):
    seen = {}

    def fake_start(*, user, passphrase=""):
        seen["user"], seen["passphrase"] = user, passphrase
        return _run(
            kind=BackupRun.Kind.MANUAL,
            status=BackupRun.Status.RUNNING,
            triggered_by=user,
        )

    monkeypatch.setattr(backup_runner, "start_manual_backup", fake_start)
    resp = auth_client(admin_user).post(
        RUN_URL, {"passphrase": "hunter2"}, format="json"
    )
    assert resp.status_code == 202
    assert resp.data["kind"] == "MANUAL" and resp.data["status"] == "RUNNING"
    assert seen == {"user": admin_user, "passphrase": "hunter2"}


def test_can_run_now_enforces_a_cooldown():
    ok, _ = backup_runner.can_run_now()
    assert ok is True
    _run(kind=BackupRun.Kind.MANUAL, status=BackupRun.Status.SUCCESS)
    ok, why = backup_runner.can_run_now()
    assert ok is False and "try again" in why


def test_start_manual_backup_refuses_cleanly_when_it_cannot_launch(
    settings, tmp_path, admin_user
):
    # No backup.ps1 under this dir (and CI is not the Windows install) — the
    # helper must raise without leaving an orphaned RUNNING row.
    settings.CAMPUS_SCRIPTS_DIR = str(tmp_path)
    with pytest.raises(backup_runner.BackupError):
        backup_runner.start_manual_backup(user=admin_user)
    assert not BackupRun.objects.filter(kind=BackupRun.Kind.MANUAL).exists()


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
