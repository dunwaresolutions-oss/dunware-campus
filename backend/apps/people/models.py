"""
Student CRM — the central people model (see docs/DATA_MODEL.md).

`Student` is the spine; guardians, emergency contacts, authorized pickups,
observations and documents hang off it. High-sensitivity fields (government
IDs, custody notes, home address, observation bodies, document files) are
AES-256-GCM encrypted at rest. Every model here is a `SensitiveModel`, so the
audit layer records reads as well as writes.

Object visibility (`is_visible_to`) is the single source of truth the DRF
`IsObjectOwnerOrStaff` permission and every queryset scope call through.
"""
from __future__ import annotations

from django.apps import apps as django_apps
from django.conf import settings
from django.db import models

from apps.accounts.models import Role
from apps.core.fields import EncryptedCharField, EncryptedTextField
from apps.core.models import BaseModel, SensitiveModel, SensitiveSoftDeleteModel
from apps.core.storage import document_storage

# Roles that see every person record.
_ADMIN_ROLES = frozenset({Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK})
_INSTRUCTOR_ROLES = frozenset({Role.TEACHER, Role.TUTOR})


def _role(user) -> str | None:
    return getattr(user, "role", None)


def _student_ids_for_instructor(user) -> set:
    """Students actively enrolled in a group this user staffs."""
    Enrolment = django_apps.get_model("registration", "Enrolment")
    group_ids = GroupStaff.objects.filter(user=user, active=True).values_list("group_id", flat=True)
    return set(
        Enrolment.objects.filter(group_id__in=group_ids, status=Enrolment.Status.ACTIVE)
        .values_list("student_id", flat=True)
    )


class Group(BaseModel):
    """Age-range-agnostic unit a student belongs to: a daycare room, a class,
    or a secondary course section. Scheduling (Phase 3) extends this."""

    class Kind(models.TextChoices):
        ROOM = "ROOM", "Daycare room"
        CLASS = "CLASS", "Class"
        SECTION = "SECTION", "Course section"

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CLASS)
    stage_label = models.CharField(
        max_length=60, blank=True, help_text="Free label, e.g. 'Toddler', 'Grade 4', 'SNC2D'."
    )
    capacity = models.PositiveIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "people_group"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class GroupStaff(BaseModel):
    """A staff member assigned to a group — drives instructor visibility."""

    class Role(models.TextChoices):
        LEAD = "LEAD", "Lead"
        ASSISTANT = "ASSISTANT", "Assistant"

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="staff")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="group_assignments"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.LEAD)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "people_group_staff"
        constraints = [
            models.UniqueConstraint(fields=["group", "user"], name="uniq_group_staff"),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.group} ({self.role})"


class Student(SensitiveSoftDeleteModel):
    class Status(models.TextChoices):
        PROSPECTIVE = "PROSPECTIVE", "Prospective"
        ENROLLED = "ENROLLED", "Enrolled"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"
        GRADUATED = "GRADUATED", "Graduated"

    PII_FIELDS = ("first_name", "last_name", "preferred_name", "date_of_birth",
                  "government_id", "custody_notes")
    PII_PURPOSE = {
        "date_of_birth": "age-band placement, ratio compliance, report cards",
        "government_id": "government reporting where legally required; encrypted",
        "custody_notes": "custody / access arrangements affecting pickup; encrypted",
    }

    # link to a login (older grades, per install) — optional
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="student_profile",
    )

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    preferred_name = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField()
    pronouns = models.CharField(max_length=40, blank=True)

    student_number = models.CharField(max_length=20, unique=True)
    government_id = EncryptedCharField(blank=True, default="")
    custody_notes = EncryptedTextField(blank=True, default="")

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROSPECTIVE)
    primary_group = models.ForeignKey(
        Group, null=True, blank=True, on_delete=models.SET_NULL, related_name="primary_students"
    )
    left_on = models.DateField(
        null=True, blank=True,
        help_text="Withdrawn / graduated date; starts the retention clock.",
    )
    legal_hold = models.BooleanField(
        default=False, help_text="Blocks retention purge and the erase-this-person action."
    )
    anonymized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "people_student"
        ordering = ["last_name", "first_name"]
        indexes = [models.Index(fields=["status", "last_name"])]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.student_number})"

    @property
    def display_name(self) -> str:
        first = self.preferred_name or self.first_name
        return f"{first} {self.last_name}".strip()

    def guardians(self):
        return Guardian.objects.filter(links__student=self)

    def is_visible_to(self, user) -> bool:
        if not (user and getattr(user, "is_authenticated", False)):
            return False
        role = _role(user)
        if role in _ADMIN_ROLES:
            return True
        if role in _INSTRUCTOR_ROLES:
            return self.pk in _student_ids_for_instructor(user)
        if role == Role.PARENT:
            return GuardianLink.objects.filter(student=self, guardian__user=user).exists()
        if role == Role.STUDENT:
            return self.user_id == user.pk
        return False

    @classmethod
    def visible_queryset(cls, user):
        base = cls.objects.alive()
        if not (user and getattr(user, "is_authenticated", False)):
            return cls.objects.none()
        role = _role(user)
        if role in _ADMIN_ROLES:
            return base
        if role in _INSTRUCTOR_ROLES:
            return base.filter(pk__in=_student_ids_for_instructor(user))
        if role == Role.PARENT:
            return base.filter(guardian_links__guardian__user=user).distinct()
        if role == Role.STUDENT:
            return base.filter(user_id=user.pk)
        return cls.objects.none()


class Guardian(SensitiveModel):
    PII_FIELDS = ("first_name", "last_name", "email", "phone", "address")
    PII_PURPOSE = {
        "email": "primary channel for announcements, incident reports, invoices",
        "phone": "urgent contact; encrypted",
        "address": "home address for records / correspondence; encrypted",
    }

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="guardian_profile",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = EncryptedCharField(blank=True, default="")
    address = EncryptedTextField(blank=True, default="")

    class Meta:
        db_table = "people_guardian"
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def is_visible_to(self, user) -> bool:
        role = _role(user)
        if role in _ADMIN_ROLES:
            return True
        if role == Role.PARENT:
            return self.user_id == user.pk
        # an instructor may see a guardian of one of their students
        if role in _INSTRUCTOR_ROLES:
            return GuardianLink.objects.filter(
                guardian=self, student_id__in=_student_ids_for_instructor(user)
            ).exists()
        return False


class GuardianLink(BaseModel):
    """Guardian ⇄ Student with the relationship and the flags that matter
    operationally: custody, pickup, who gets the emails."""

    class Relationship(models.TextChoices):
        MOTHER = "MOTHER", "Mother"
        FATHER = "FATHER", "Father"
        PARENT = "PARENT", "Parent"
        GRANDPARENT = "GRANDPARENT", "Grandparent"
        LEGAL_GUARDIAN = "LEGAL_GUARDIAN", "Legal guardian"
        FOSTER = "FOSTER", "Foster carer"
        OTHER = "OTHER", "Other"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="guardian_links")
    guardian = models.ForeignKey(Guardian, on_delete=models.CASCADE, related_name="links")
    relationship = models.CharField(max_length=16, choices=Relationship.choices)
    is_primary_contact = models.BooleanField(default=False)
    has_custody = models.BooleanField(default=True)
    can_pickup = models.BooleanField(default=True)
    receives_communications = models.BooleanField(default=True)
    lives_with = models.BooleanField(default=True)
    custody_notes = EncryptedTextField(blank=True, default="")

    class Meta:
        db_table = "people_guardian_link"
        constraints = [
            models.UniqueConstraint(fields=["student", "guardian"], name="uniq_student_guardian"),
        ]

    def __str__(self) -> str:
        return f"{self.guardian} → {self.student} ({self.relationship})"


class EmergencyContact(SensitiveModel):
    PII_FIELDS = ("name", "phone", "alt_phone")

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="emergency_contacts"
    )
    name = models.CharField(max_length=150)
    relationship = models.CharField(max_length=60)
    phone = EncryptedCharField(blank=True, default="")
    alt_phone = EncryptedCharField(blank=True, default="")
    priority = models.PositiveSmallIntegerField(default=1)

    class Meta:
        db_table = "people_emergency_contact"
        ordering = ["priority"]

    def __str__(self) -> str:
        return f"{self.name} (emergency for {self.student_id})"

    def is_visible_to(self, user) -> bool:
        return self.student.is_visible_to(user)


class AuthorizedPickup(SensitiveModel):
    """People allowed to collect a student. Attendance check-out (Phase 3)
    validates against this list."""

    PII_FIELDS = ("name", "phone")

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="authorized_pickups"
    )
    name = models.CharField(max_length=150)
    relationship = models.CharField(max_length=60)
    phone = EncryptedCharField(blank=True, default="")
    note = models.CharField(max_length=255, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "people_authorized_pickup"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} may collect {self.student_id}"

    def is_visible_to(self, user) -> bool:
        return self.student.is_visible_to(user)


class Observation(SensitiveSoftDeleteModel):
    """A dated note about a student. `visible_to_guardians` gates whether it
    surfaces in the parent portal (Phase 6)."""

    PII_FIELDS = ("body",)

    class Category(models.TextChoices):
        DEVELOPMENTAL = "DEVELOPMENTAL", "Developmental"
        BEHAVIOURAL = "BEHAVIOURAL", "Behavioural"
        ACADEMIC = "ACADEMIC", "Academic"
        INCIDENT = "INCIDENT", "Incident"
        MEDICAL = "MEDICAL", "Medical"
        GENERAL = "GENERAL", "General"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="observations")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    category = models.CharField(max_length=14, choices=Category.choices, default=Category.GENERAL)
    occurred_at = models.DateTimeField()
    body = EncryptedTextField()
    visible_to_guardians = models.BooleanField(default=False)

    class Meta:
        db_table = "people_observation"
        ordering = ["-occurred_at"]

    def __str__(self) -> str:
        return f"{self.category} note on {self.student_id} @ {self.occurred_at:%Y-%m-%d}"

    def is_visible_to(self, user) -> bool:
        role = _role(user)
        if role == Role.PARENT:
            return self.visible_to_guardians and self.student.is_visible_to(user)
        return self.student.is_visible_to(user)


class Document(SensitiveSoftDeleteModel):
    """A file attached to a student. Bytes are AES-GCM encrypted on disk via
    `EncryptedFileSystemStorage`."""

    PII_FIELDS = ("title", "file")

    class Kind(models.TextChoices):
        BIRTH_CERTIFICATE = "BIRTH_CERTIFICATE", "Birth certificate"
        IMMUNIZATION = "IMMUNIZATION", "Immunization record"
        CUSTODY_ORDER = "CUSTODY_ORDER", "Custody / court order"
        IEP = "IEP", "IEP / support plan"
        PHOTO = "PHOTO", "Photo"
        CONSENT_FORM = "CONSENT_FORM", "Signed consent form"
        OTHER = "OTHER", "Other"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to="documents/%Y/%m/", storage=document_storage)
    content_type = models.CharField(max_length=100, blank=True)
    byte_size = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "people_document"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.title}"

    def is_visible_to(self, user) -> bool:
        return self.student.is_visible_to(user)
