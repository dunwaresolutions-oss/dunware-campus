"""
Individual Education Plans.

An IEP is a teaching document: the goals, accommodations, and services a
student needs, plus the record of each review. Unlike clinical health data it
is not gated behind a named-staff grant — every teacher of the student must be
able to read it to implement it — but the substance is still
``EncryptedTextField`` and every read is audited (``SensitiveModel``).

Guardians see ACTIVE / UNDER_REVIEW plans for their own child through the
portal dashboard, never the staff API.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.accounts.models import Role
from apps.core.fields import EncryptedTextField
from apps.core.models import SensitiveModel, SensitiveSoftDeleteModel
from apps.people.models import Student

_ADMIN_ROLES = frozenset({Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK})
_INSTRUCTOR_ROLES = frozenset({Role.TEACHER, Role.TUTOR})


class IEP(SensitiveSoftDeleteModel):
    PII_FIELDS = ("strengths", "needs", "summary")

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        ARCHIVED = "ARCHIVED", "Archived"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="ieps")
    school_year = models.CharField(max_length=20, blank=True)  # "2026–2027"
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    primary_concern = models.CharField(max_length=200, blank=True)

    start_date = models.DateField(null=True, blank=True)
    review_date = models.DateField(null=True, blank=True)  # next scheduled review
    end_date = models.DateField(null=True, blank=True)

    strengths = EncryptedTextField(blank=True, default="")
    needs = EncryptedTextField(blank=True, default="")
    summary = EncryptedTextField(blank=True, default="")

    case_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        db_table = "iep_iep"
        ordering = ["-start_date", "-created_at"]
        indexes = [models.Index(fields=["student", "status"])]

    def __str__(self) -> str:
        return f"IEP for {self.student_id} ({self.status})"

    def is_visible_to(self, user) -> bool:
        role = getattr(user, "role", None)
        if role in _ADMIN_ROLES:
            return True
        if role in _INSTRUCTOR_ROLES:
            return self.student.is_visible_to(user)
        if role == Role.PARENT:
            return self.status in (self.Status.ACTIVE, self.Status.UNDER_REVIEW) and \
                self.student.is_visible_to(user)
        return False


class _IEPChild(SensitiveModel):
    iep = models.ForeignKey(IEP, on_delete=models.CASCADE, related_name="%(class)ss")

    class Meta:
        abstract = True

    def is_visible_to(self, user) -> bool:
        return self.iep.is_visible_to(user)


class IEPGoal(_IEPChild):
    PII_FIELDS = ("description", "baseline", "target", "progress_notes")

    class Area(models.TextChoices):
        READING = "READING", "Reading"
        WRITING = "WRITING", "Writing"
        MATH = "MATH", "Mathematics"
        COMMUNICATION = "COMMUNICATION", "Communication / language"
        SOCIAL_EMOTIONAL = "SOCIAL_EMOTIONAL", "Social / emotional"
        BEHAVIOUR = "BEHAVIOUR", "Behaviour / self-regulation"
        MOTOR = "MOTOR", "Fine / gross motor"
        ORGANISATION = "ORGANISATION", "Organisation / executive function"
        LIFE_SKILLS = "LIFE_SKILLS", "Life / independence skills"
        OTHER = "OTHER", "Other"

    class Progress(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", "Not started"
        EMERGING = "EMERGING", "Emerging"
        PROGRESSING = "PROGRESSING", "Progressing"
        MET = "MET", "Met"
        DISCONTINUED = "DISCONTINUED", "Discontinued"

    area = models.CharField(max_length=20, choices=Area.choices, default=Area.OTHER)
    description = EncryptedTextField()
    baseline = EncryptedTextField(blank=True, default="")
    target = EncryptedTextField(blank=True, default="")
    progress = models.CharField(
        max_length=12, choices=Progress.choices, default=Progress.NOT_STARTED
    )
    progress_notes = EncryptedTextField(blank=True, default="")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "iep_goal"
        ordering = ["order", "created_at"]

    def __str__(self) -> str:
        return f"{self.area} goal on IEP {self.iep_id}"


class IEPAccommodation(_IEPChild):
    PII_FIELDS = ("description",)

    class Category(models.TextChoices):
        PRESENTATION = "PRESENTATION", "Presentation"
        RESPONSE = "RESPONSE", "Response"
        SETTING = "SETTING", "Setting / environment"
        TIMING = "TIMING", "Timing / scheduling"
        ASSISTIVE_TECH = "ASSISTIVE_TECH", "Assistive technology"
        OTHER = "OTHER", "Other"

    category = models.CharField(
        max_length=16, choices=Category.choices, default=Category.OTHER
    )
    description = EncryptedTextField()
    applies_to = models.CharField(max_length=120, blank=True, default="All classes")
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "iep_accommodation"
        ordering = ["category", "created_at"]

    def __str__(self) -> str:
        return f"{self.category} accommodation on IEP {self.iep_id}"


class IEPService(_IEPChild):
    PII_FIELDS = ("notes",)

    service = models.CharField(max_length=150)  # "Speech-language therapy"
    provider = models.CharField(max_length=150, blank=True)
    frequency = models.CharField(max_length=120, blank=True)  # "2 × 30 min / week"
    location = models.CharField(max_length=120, blank=True)  # "Resource room"
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    notes = EncryptedTextField(blank=True, default="")

    class Meta:
        db_table = "iep_service"
        ordering = ["service", "created_at"]

    def __str__(self) -> str:
        return f"{self.service} on IEP {self.iep_id}"


class IEPReview(_IEPChild):
    PII_FIELDS = ("notes",)

    class Outcome(models.TextChoices):
        CONTINUE = "CONTINUE", "Continue as written"
        REVISE = "REVISE", "Revise the plan"
        EXIT = "EXIT", "Exit / discontinue"
        REFER = "REFER", "Refer for further assessment"

    review_date = models.DateField()
    attendees = models.CharField(max_length=255, blank=True)
    outcome = models.CharField(max_length=10, choices=Outcome.choices, default=Outcome.CONTINUE)
    notes = EncryptedTextField(blank=True, default="")
    next_review_date = models.DateField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        db_table = "iep_review"
        ordering = ["-review_date"]

    def __str__(self) -> str:
        return f"review {self.review_date} on IEP {self.iep_id}"
