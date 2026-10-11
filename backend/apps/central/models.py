"""
Campus Central's own data model (C3). See docs/CENTRAL_SYNC_SCOPE.md for the
field list every ``Central*`` read table below mirrors exactly, and
apps/core/central_export.py (on the Campus/school side) for the matching
export-bundle row shapes these tables exist to receive.

No ingest endpoint exists yet (C4) -- nothing writes to a ``Central*`` table
outside tests. ``School.pk`` (a UUID, inherited from ``apps.core.BaseModel``)
*is* the ``school_id`` a linked Campus install stores in its own
``SiteConfiguration.school_id`` -- there is deliberately no separate,
redundant ``school_id`` field on this side; Central mints the id by creating
the row.
"""
from __future__ import annotations

import hashlib
import secrets

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class CentralSettings(BaseModel):
    """This Head Office install's own identity. Singleton, same pattern as
    Campus's ``SchoolProfile``/``SiteConfiguration``."""

    name = models.CharField(max_length=200, blank=True)
    region = models.CharField(max_length=120, blank=True)
    # The newest snapshot schema this Central build understands. C4's ingest
    # refuses a bundle whose own snapshot_schema_version is newer than this
    # (see docs/CENTRAL_SYNC_SCOPE.md's sync mechanism / versioning note) --
    # not enforced anywhere yet, just the value C4 will read.
    snapshot_schema_version_supported = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "central_settings"
        verbose_name = "Central settings"

    def __str__(self) -> str:
        return self.name or "Campus Central (unset)"

    def save(self, *args, **kwargs):
        if self._state.adding and CentralSettings.objects.exists():
            from django.core.exceptions import ValidationError

            raise ValidationError("CentralSettings is a singleton — edit the existing row.")
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> CentralSettings:
        obj = cls.objects.first()
        return obj if obj is not None else cls.objects.create()


class School(BaseModel):
    """The registry of schools linked to this Head Office. ``pk`` is the
    ``school_id`` issued to a school when it's registered here -- a school's
    own ``SiteConfiguration.school_id`` is a copy of this id, never the
    other way around."""

    class SyncStatus(models.TextChoices):
        NEVER_SYNCED = "NEVER_SYNCED", "Never synced"
        OK = "OK", "OK"
        ERROR = "ERROR", "Error"

    name = models.CharField(max_length=200)
    district = models.CharField(max_length=120, blank=True)
    # SHA-256 hex digest of the bearer token -- a fast hash, not a slow
    # password hasher, is the right tool here: the token is a high-entropy
    # random value Central itself generates (see issue_token()), not a
    # low-entropy human password vulnerable to offline guessing. Central
    # only ever needs to VERIFY a presented token, never recover it.
    sync_token_hash = models.CharField(max_length=64, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    sync_status = models.CharField(
        max_length=12, choices=SyncStatus.choices, default=SyncStatus.NEVER_SYNCED
    )
    # The snapshot_schema_version this school last successfully synced in —
    # set by C4's ingest, not here.
    snapshot_schema_version = models.PositiveIntegerField(null=True, blank=True)
    contact_email = models.EmailField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "central_school"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.district})" if self.district else self.name

    @staticmethod
    def _hash(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    def issue_token(self) -> str:
        """Generates a fresh bearer token, stores only its hash, and returns
        the plaintext once -- the caller (the school registry UI/command,
        C4+) is responsible for showing it to whoever is setting up the
        school's own `link_central`, since it can never be shown again."""
        raw = secrets.token_urlsafe(32)
        self.sync_token_hash = self._hash(raw)
        self.save(update_fields=["sync_token_hash", "updated_at"])
        return raw

    def verify_token(self, raw_token: str) -> bool:
        if not self.sync_token_hash or not raw_token:
            return False
        return secrets.compare_digest(self._hash(raw_token), self.sync_token_hash)


class DistrictAssignment(BaseModel):
    """Which island/district a ``DISTRICT_OFFICER`` may see (C6). Meaningless
    for ``MINISTRY_ADMIN``/``MINISTRY_ANALYST``, who see every district --
    only read for a user whose role is actually ``DISTRICT_OFFICER``
    (apps/central/permissions.py's scoping helpers), never enforced by this
    model itself. A user can hold more than one assignment (an officer
    covering several islands); they then see the union."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="central_district_assignments",
    )
    district = models.CharField(max_length=120)

    class Meta:
        db_table = "central_district_assignment"
        constraints = [
            models.UniqueConstraint(fields=["user", "district"], name="uniq_district_assignment"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.district}"


class SnapshotBatch(BaseModel):
    """One row per received sync bundle. ``created_at`` (from ``BaseModel``)
    is when Central received it -- there is no separate ``received_at``
    field, since a batch is only ever created once, at receipt."""

    class Kind(models.TextChoices):
        FULL = "FULL", "Full"
        INCREMENTAL = "INCREMENTAL", "Incremental"

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="batches")
    kind = models.CharField(max_length=11, choices=Kind.choices)
    manifest = models.JSONField(default=dict)
    content_hash = models.CharField(max_length=64, db_index=True)
    applied = models.BooleanField(default=False)
    rejected_reason = models.TextField(blank=True)

    class Meta:
        db_table = "central_snapshot_batch"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        state = "applied" if self.applied else "pending/rejected"
        return f"{self.kind} batch for {self.school_id} ({state})"


class SchoolScopedModel(BaseModel):
    """Shared shape for every ``Central*`` read table: tagged by the school
    it came from, keyed to the original row on that school's own database
    by ``source_id`` (never Central's own ``id``, which only identifies
    Central's copy) so a re-synced bundle upserts instead of duplicating."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="+")
    source_id = models.UUIDField()
    upserted_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CentralStudent(SchoolScopedModel):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    student_number = models.CharField(max_length=20)
    status = models.CharField(max_length=12)
    primary_group_source_id = models.UUIDField(null=True, blank=True)
    guardian_count = models.PositiveIntegerField(default=0)
    source_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "central_student"
        constraints = [
            models.UniqueConstraint(fields=["school", "source_id"], name="uniq_central_student"),
        ]
        indexes = [models.Index(fields=["school", "last_name", "first_name"])]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} ({self.school_id})"


class CentralGuardian(SchoolScopedModel):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    # [{"student_id": "<uuid str>", "relationship": "PARENT"}, ...]
    children = models.JSONField(default=list)
    source_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "central_guardian"
        constraints = [
            models.UniqueConstraint(fields=["school", "source_id"], name="uniq_central_guardian"),
        ]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} ({self.school_id})"


class CentralStaff(SchoolScopedModel):
    username = models.CharField(max_length=150)
    role = models.CharField(max_length=16)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "central_staff"
        constraints = [
            models.UniqueConstraint(fields=["school", "source_id"], name="uniq_central_staff"),
        ]

    def __str__(self) -> str:
        return f"{self.username} ({self.school_id})"


class CentralGroup(SchoolScopedModel):
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10)
    stage_label = models.CharField(max_length=60, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)
    live_count = models.PositiveIntegerField(default=0)
    source_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "central_group"
        constraints = [
            models.UniqueConstraint(fields=["school", "source_id"], name="uniq_central_group"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.school_id})"


class CentralEnrolment(SchoolScopedModel):
    student_source_id = models.UUIDField()
    group_source_id = models.UUIDField()
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=8)
    source_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "central_enrolment"
        constraints = [
            models.UniqueConstraint(fields=["school", "source_id"], name="uniq_central_enrolment"),
        ]
        indexes = [models.Index(fields=["school", "student_source_id"])]


class CentralConsent(SchoolScopedModel):
    student_source_id = models.UUIDField()
    kind = models.CharField(max_length=20)
    version = models.CharField(max_length=20)
    granted = models.BooleanField()
    recorded_at = models.DateTimeField()
    source_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "central_consent"
        constraints = [
            models.UniqueConstraint(fields=["school", "source_id"], name="uniq_central_consent"),
        ]
        indexes = [models.Index(fields=["school", "student_source_id"])]


class CentralReportCard(SchoolScopedModel):
    student_source_id = models.UUIDField()
    term_source_id = models.UUIDField()
    status = models.CharField(max_length=10)
    source_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "central_report_card"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "source_id"], name="uniq_central_report_card"
            ),
        ]


class CentralRegistrationCounts(BaseModel):
    """Aggregate, not source-row-keyed (there is no single "registration
    counts" row on the school side to track by id) -- one row per school,
    fully replaced on every sync."""

    school = models.OneToOneField(
        School, on_delete=models.CASCADE, related_name="registration_counts"
    )
    applications_by_status = models.JSONField(default=dict)
    waitlist_by_group = models.JSONField(default=dict)
    upserted_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "central_registration_counts"

    def __str__(self) -> str:
        return f"registration counts for {self.school_id}"


class CentralAttendanceSummary(BaseModel):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="+")
    student_source_id = models.UUIDField()
    term_source_id = models.UUIDField()
    present = models.PositiveIntegerField(default=0)
    absent = models.PositiveIntegerField(default=0)
    late = models.PositiveIntegerField(default=0)
    present_pct = models.FloatField(null=True, blank=True)
    upserted_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "central_attendance_summary"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "student_source_id", "term_source_id"],
                name="uniq_central_attendance_summary",
            ),
        ]


class CentralIncidentSummary(BaseModel):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="+")
    term_source_id = models.UUIDField()
    category = models.CharField(max_length=13)
    severity = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=12)
    count = models.PositiveIntegerField(default=0)
    upserted_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "central_incident_summary"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "term_source_id", "category", "severity", "status"],
                name="uniq_central_incident_summary",
            ),
        ]


class CentralBillingSummary(BaseModel):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="+")
    term_source_id = models.UUIDField()
    issued_cents = models.PositiveIntegerField(default=0)
    paid_cents = models.PositiveIntegerField(default=0)
    outstanding_cents = models.PositiveIntegerField(default=0)
    upserted_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "central_billing_summary"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "term_source_id"], name="uniq_central_billing_summary"
            ),
        ]
