"""
Daily attendance with check-in / check-out (see docs/DATA_MODEL.md).

One `AttendanceRecord` per student per day per group. Check-out is only
accepted for someone on the student's `AuthorizedPickup` list or a guardian
flagged `can_pickup` — enforced in `apps/attendance/services.py`, recorded
here, and audited. The "who collected this child, and when" trail is
sensitive, so the model is a `SensitiveModel` and its reads are logged.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.accounts.models import Role
from apps.core.models import SensitiveModel
from apps.people.models import AuthorizedPickup, Group, GuardianLink, Student


class AttendanceRecord(SensitiveModel):
    PII_FIELDS = ("dropped_off_by_name", "collected_by_name", "note")

    class Status(models.TextChoices):
        EXPECTED = "EXPECTED", "Expected"
        PRESENT = "PRESENT", "Present"
        ABSENT = "ABSENT", "Absent"
        LATE = "LATE", "Late"
        EXCUSED = "EXCUSED", "Excused absence"
        LEFT_EARLY = "LEFT_EARLY", "Left early"

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="attendance_records"
    )
    group = models.ForeignKey(
        Group, on_delete=models.PROTECT, related_name="attendance_records"
    )
    date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.EXPECTED)

    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    dropped_off_by_name = models.CharField(max_length=150, blank=True)

    checked_out_at = models.DateTimeField(null=True, blank=True)
    checked_out_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    collected_by_pickup = models.ForeignKey(
        AuthorizedPickup, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    collected_by_guardian = models.ForeignKey(
        GuardianLink, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    collected_by_name = models.CharField(max_length=150, blank=True)

    note = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "attendance_record"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "group", "date"], name="uniq_attendance_per_day"
            ),
        ]
        indexes = [models.Index(fields=["group", "date"]), models.Index(fields=["date", "status"])]

    def __str__(self) -> str:
        return f"{self.student_id} {self.date} {self.status}"

    @property
    def is_checked_in(self) -> bool:
        return self.checked_in_at is not None and self.checked_out_at is None

    def is_visible_to(self, user) -> bool:
        role = getattr(user, "role", None)
        if role == Role.PARENT:
            return self.student.is_visible_to(user)
        return self.student.is_visible_to(user)
