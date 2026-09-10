"""Record a backup / restore-verify run so the console can show backup health.

Called by ``deploy\\backup.ps1`` (kind SCHEDULED / MANUAL) and
``deploy\\restore.ps1`` (kind VERIFY), on success and on failure. Prints the
run id on stdout so a caller can pass ``--run-id`` back to flip an earlier
RUNNING row to SUCCESS / FAILED.

    campus-app.exe manage record_backup --status SUCCESS --archive campus-….zip.gpg \
        --size 40317122 --database-ok --media-ok --retained 14
    campus-app.exe manage record_backup --status FAILED  --error "pg_dump exited 1"
"""
from __future__ import annotations

import platform

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.reporting.models import BackupRun

_KEEP_DEFAULT = 200


class Command(BaseCommand):
    help = "Record a backup or restore-verification run."

    def add_arguments(self, parser):
        parser.add_argument("--status", required=True,
                            choices=["RUNNING", "SUCCESS", "FAILED"])
        parser.add_argument("--kind", default="SCHEDULED",
                            choices=["SCHEDULED", "MANUAL", "VERIFY"])
        parser.add_argument("--run-id", default=None,
                            help="Update this earlier run instead of creating a new one.")
        parser.add_argument("--archive", default="")
        parser.add_argument("--size", type=int, default=None)
        parser.add_argument("--database-ok", action="store_true")
        parser.add_argument("--media-ok", action="store_true")
        parser.add_argument("--no-encryption", action="store_true")
        parser.add_argument("--retained", type=int, default=None)
        parser.add_argument("--error", default="")
        parser.add_argument("--started", default=None, help="ISO-8601 start time.")
        parser.add_argument("--host", default="")
        parser.add_argument("--build", default="")
        parser.add_argument("--keep", type=int, default=_KEEP_DEFAULT,
                            help="Keep only the newest N rows (0 = keep all).")

    def handle(self, *args, **o):
        now = timezone.now()
        fields = dict(
            kind=o["kind"],
            status=o["status"],
            archive_name=(o["archive"] or "")[:200],
            size_bytes=o["size"],
            database_ok=o["database_ok"],
            media_ok=o["media_ok"],
            encrypted=not o["no_encryption"],
            archives_retained=o["retained"],
            error=(o["error"] or "")[:5000],
            host=(o["host"] or platform.node())[:100],
            build=(o["build"] or "")[:60],
            finished_at=None if o["status"] == "RUNNING" else now,
        )

        run = BackupRun.objects.filter(pk=o["run_id"]).first() if o["run_id"] else None
        if run is not None:
            for k, v in fields.items():
                setattr(run, k, v)
            run.save()
        else:
            started = (parse_datetime(o["started"]) if o["started"] else None) or now
            run = BackupRun.objects.create(started_at=started, **fields)

        keep = o["keep"]
        if keep and BackupRun.objects.count() > keep:
            stale = list(
                BackupRun.objects.order_by("-started_at").values_list("pk", flat=True)[keep:]
            )
            BackupRun.objects.filter(pk__in=stale).delete()

        self.stdout.write(str(run.pk))
