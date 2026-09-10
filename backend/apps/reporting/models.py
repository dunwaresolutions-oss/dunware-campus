"""Operational history the console can show — currently: backup runs.

``deploy\\backup.ps1`` and ``deploy\\restore.ps1`` call
``campus-app.exe manage record_backup ...`` so an operator can see whether
backups are actually happening, when the last one succeeded, and whether a
restore has ever been verified. Nothing here is PII — it describes the box,
not a person, so it is a plain ``BaseModel`` (no encryption, no read audit).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class BackupRun(BaseModel):
    class Kind(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        MANUAL = "MANUAL", "Manual"
        VERIFY = "VERIFY", "Restore verification"

    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"

    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SCHEDULED)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    archive_name = models.CharField(max_length=200, blank=True)  # basename only
    size_bytes = models.BigIntegerField(null=True, blank=True)
    database_ok = models.BooleanField(default=False)
    media_ok = models.BooleanField(default=False)
    encrypted = models.BooleanField(default=True)
    archives_retained = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)

    host = models.CharField(max_length=100, blank=True)
    build = models.CharField(max_length=60, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        db_table = "reporting_backup_run"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["status", "started_at"]),
            models.Index(fields=["kind", "started_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.kind} backup {self.status} @ {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at and self.started_at:
            return round((self.finished_at - self.started_at).total_seconds(), 1)
        return None
