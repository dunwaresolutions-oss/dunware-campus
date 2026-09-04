"""
Registration lifecycle: application → review → offer/waitlist → enrolment, plus
versioned consent capture and pre-enrolment document upload.

`Enrolment` is the authoritative "this student belongs to this group for this
span" record; scheduling / attendance / grades all read it. Consent is
**append-only in spirit**: a change of mind is a new row, and
`Consent.current_for(student, kind)` returns the latest.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.fields import EncryptedCharField, EncryptedTextField
from apps.core.models import BaseModel, SensitiveModel, SensitiveSoftDeleteModel
from apps.core.storage import document_storage
from apps.people.models import Group, Guardian, Student

_ADMIN_ROLES = frozenset({Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK})


class Application(SensitiveSoftDeleteModel):
    """A prospective family's request for a place. Holds child + applicant
    detail before a `Student` record exists."""

    PII_FIELDS = ("child_first_name", "child_last_name", "child_date_of_birth",
                  "applicant_name", "applicant_email", "applicant_phone", "notes")

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        OFFER_MADE = "OFFER_MADE", "Offer made"
        WAITLISTED = "WAITLISTED", "Waitlisted"
        ENROLLED = "ENROLLED", "Enrolled"
        DECLINED = "DECLINED", "Declined"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"

    TERMINAL = {Status.ENROLLED, Status.DECLINED, Status.WITHDRAWN}

    child_first_name = models.CharField(max_length=100)
    child_last_name = models.CharField(max_length=100)
    child_date_of_birth = models.DateField()
    desired_start = models.DateField(null=True, blank=True)
    desired_group = models.ForeignKey(
        Group, null=True, blank=True, on_delete=models.SET_NULL, related_name="applications"
    )

    applicant_name = models.CharField(max_length=200)
    applicant_email = models.EmailField()
    applicant_phone = EncryptedCharField(blank=True, default="")
    notes = EncryptedTextField(blank=True, default="")

    status = models.CharField(max_length=14, choices=Status.choices, default=Status.SUBMITTED)
    submitted_at = models.DateTimeField(default=timezone.now)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    student = models.ForeignKey(
        Student, null=True, blank=True, on_delete=models.SET_NULL, related_name="applications"
    )

    class Meta:
        db_table = "registration_application"
        ordering = ["-submitted_at"]

    def __str__(self) -> str:
        return f"application: {self.child_first_name} {self.child_last_name} ({self.status})"

    def is_visible_to(self, user) -> bool:
        return getattr(user, "role", None) in _ADMIN_ROLES


class ApplicationDocument(SensitiveModel):
    PII_FIELDS = ("title", "file")

    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="documents"
    )
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to="applications/%Y/%m/", storage=document_storage)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "registration_application_document"

    def __str__(self) -> str:
        return f"{self.title} ({self.application_id})"

    def is_visible_to(self, user) -> bool:
        return self.application.is_visible_to(user)


class WaitlistEntry(BaseModel):
    application = models.OneToOneField(
        Application, on_delete=models.CASCADE, related_name="waitlist_entry"
    )
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="waitlist")
    priority = models.IntegerField(default=100, help_text="Lower sorts first.")
    added_at = models.DateTimeField(default=timezone.now)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "registration_waitlist_entry"
        ordering = ["priority", "added_at"]
        verbose_name_plural = "waitlist entries"

    def __str__(self) -> str:
        return f"waitlist: {self.application_id} for {self.group_id} (#{self.priority})"


class Offer(BaseModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        DECLINED = "DECLINED", "Declined"
        EXPIRED = "EXPIRED", "Expired"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="offers")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="offers")
    start_date = models.DateField()
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    made_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "registration_offer"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"offer: {self.application_id} → {self.group_id} ({self.status})"

    @property
    def is_open(self) -> bool:
        return self.status == self.Status.PENDING and self.expires_at > timezone.now()


class Enrolment(BaseModel):
    """Authoritative student ⇄ group membership over a span of time."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ENDED = "ENDED", "Ended"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrolments")
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="enrolments")
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    source_application = models.ForeignKey(
        Application, null=True, blank=True, on_delete=models.SET_NULL, related_name="enrolments"
    )

    class Meta:
        db_table = "registration_enrolment"
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["group", "status"]),
            models.Index(fields=["student", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "group"],
                condition=models.Q(status="ACTIVE"),
                name="uniq_active_enrolment_per_group",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student_id} in {self.group_id} ({self.status})"

    def end(self, on=None):
        self.end_date = on or timezone.localdate()
        self.status = self.Status.ENDED
        self.save(update_fields=["end_date", "status"])


class ConsentQuerySet(models.QuerySet):
    def current_for(self, student, kind):
        return self.filter(student=student, kind=kind).order_by("-recorded_at").first()


class Consent(SensitiveModel):
    """Versioned consent. Never updated in place — record a new row when a
    guardian grants, withdraws, or re-consents to a new version."""

    PII_FIELDS = ("granted_by_name", "notes")

    class Kind(models.TextChoices):
        PHOTO = "PHOTO", "Photography"
        MEDIA = "MEDIA", "Media / publicity"
        FIELD_TRIP = "FIELD_TRIP", "Off-site excursions"
        DATA_SHARING = "DATA_SHARING", "Information sharing with third parties"
        MEDICAL_TREATMENT = "MEDICAL_TREATMENT", "Emergency medical treatment"
        TECHNOLOGY = "TECHNOLOGY", "Technology / internet use"
        SUNSCREEN = "SUNSCREEN", "Sunscreen / topical application"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="consents")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    version = models.CharField(max_length=20, default="1")
    granted = models.BooleanField()
    granted_by = models.ForeignKey(
        Guardian, null=True, blank=True, on_delete=models.SET_NULL, related_name="consents_given"
    )
    granted_by_name = models.CharField(max_length=200, blank=True)  # snapshot
    recorded_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    notes = EncryptedTextField(blank=True, default="")

    objects = ConsentQuerySet.as_manager()

    class Meta:
        db_table = "registration_consent"
        ordering = ["-recorded_at"]
        indexes = [models.Index(fields=["student", "kind", "recorded_at"])]

    def __str__(self) -> str:
        state = "granted" if self.granted else "withdrawn"
        return f"consent {self.kind} v{self.version} {state} for {self.student_id}"

    def is_visible_to(self, user) -> bool:
        role = getattr(user, "role", None)
        if role in _ADMIN_ROLES:
            return True
        if role == Role.PARENT:
            return self.student.is_visible_to(user)
        return False

    @classmethod
    def current_for(cls, student, kind):
        return cls.objects.current_for(student, kind)
