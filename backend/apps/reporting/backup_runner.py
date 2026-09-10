"""Launch deploy/backup.ps1 for an on-demand backup requested from the console.

Why the indirection: the "Campus App" Windows service does not hold the backup
passphrase — by design it lives with the scheduled task, or the operator types
it in for this one run. We never store what the caller sends; it is handed to
backup.ps1 through the child process environment and is gone once the child
exits. The heavy lifting (pg_dump, gpg, retention) stays in the same PowerShell
script the nightly backup uses, so a manual run and a scheduled run are the
exact same code path — only ``Kind`` differs.

The child is detached: the HTTP request returns immediately with a RUNNING
``BackupRun`` row, and backup.ps1 flips that same row to SUCCESS / FAILED via
``manage record_backup --run-id`` when it finishes. Poll ``GET /api/backups/``
for the outcome.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import BackupRun

# Keep the button from being a disk-fill lever: one on-demand run per window.
COOLDOWN_SECONDS = 10 * 60
# A RUNNING row older than this never completed — the script failed to start
# (e.g. a stale on-disk backup.ps1 that rejects -RunId), crashed before its
# try/catch, or the box was rebooted mid-run. Flip it to FAILED so it stops
# showing as "running" forever and stops blocking the next on-demand run.
STALE_RUNNING_SECONDS = 30 * 60

_STALE_MESSAGE = (
    "No completion was reported within 30 minutes. The backup script likely "
    "failed to start or was interrupted — check that C:\\ProgramData\\Campus\\"
    "scripts\\backup.ps1 is current (repair-campus.ps1 -RefreshScriptsFrom) "
    "and look at the Campus App service log."
)


class BackupError(RuntimeError):
    """The backup could not be launched — the message is safe to show the user."""


def reconcile_stale_runs(now=None) -> int:
    """Flip abandoned RUNNING rows to FAILED. Idempotent; returns how many."""
    now = now or timezone.now()
    cutoff = now - dt.timedelta(seconds=STALE_RUNNING_SECONDS)
    return BackupRun.objects.filter(
        status=BackupRun.Status.RUNNING, started_at__lt=cutoff
    ).update(status=BackupRun.Status.FAILED, error=_STALE_MESSAGE)


def script_path() -> Path:
    return Path(settings.CAMPUS_SCRIPTS_DIR) / "backup.ps1"


def can_run_now(now=None) -> tuple[bool, str]:
    """(ok, reason) — whether a fresh on-demand backup may start right now."""
    now = now or timezone.now()
    running = (
        BackupRun.objects.filter(
            kind=BackupRun.Kind.MANUAL, status=BackupRun.Status.RUNNING
        )
        .order_by("-started_at")
        .first()
    )
    if running and (now - running.started_at).total_seconds() < STALE_RUNNING_SECONDS:
        return False, "A manual backup is already running. Give it a few minutes."

    last = (
        BackupRun.objects.filter(kind=BackupRun.Kind.MANUAL)
        .order_by("-started_at")
        .first()
    )
    if last:
        elapsed = (now - last.started_at).total_seconds()
        if elapsed < COOLDOWN_SECONDS:
            mins = int((COOLDOWN_SECONDS - elapsed) // 60) + 1
            return False, (
                f"An on-demand backup ran a few minutes ago — try again in "
                f"{mins} minute(s)."
            )
    return True, ""


def start_manual_backup(*, user, passphrase: str = "") -> BackupRun:
    """Spawn backup.ps1 (Kind=MANUAL) and return its RUNNING BackupRun row.

    Raises BackupError (nothing recorded) if the run can't even be launched.
    """
    if sys.platform != "win32":
        raise BackupError(
            "On-demand backups run only on the Windows install — backup.ps1 "
            "needs pg_dump and gpg on the server."
        )
    script = script_path()
    if not script.is_file():
        raise BackupError(f"backup.ps1 was not found at {script}.")
    if not passphrase and not os.environ.get("CAMPUS_BACKUP_PASSPHRASE"):
        raise BackupError(
            "No backup passphrase. Enter it below, or set CAMPUS_BACKUP_PASSPHRASE "
            "for the Campus App service so on-demand backups don't need it typed in."
        )

    run = BackupRun.objects.create(
        kind=BackupRun.Kind.MANUAL,
        status=BackupRun.Status.RUNNING,
        started_at=timezone.now(),
        triggered_by=user,
        encrypted=True,
    )

    args = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(script),
        "-InstallRoot", str(settings.INSTALL_ROOT),
        "-Out", str(settings.CAMPUS_BACKUP_DIR),
        "-Kind", "MANUAL",
        "-RunId", str(run.pk),
    ]
    child_env = os.environ.copy()
    if passphrase:
        child_env["CAMPUS_BACKUP_PASSPHRASE"] = passphrase

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
        subprocess, "DETACHED_PROCESS", 0
    )
    try:
        subprocess.Popen(  # noqa: S603 - fixed argv, shell=False, passphrase via env
            args,
            env=child_env,
            cwd=str(settings.INSTALL_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    except OSError as exc:
        run.status = BackupRun.Status.FAILED
        run.finished_at = timezone.now()
        run.error = f"Could not launch backup.ps1: {exc}"[:5000]
        run.save(update_fields=["status", "finished_at", "error"])
        raise BackupError(run.error) from exc

    return run
