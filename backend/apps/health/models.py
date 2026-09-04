"""
Health records — every clinical detail is AES-256-GCM encrypted at rest, and
access is gated to a **named staff subset** (`HealthAccessGrant`) on top of the
normal staff + MFA requirement. Reads are audited like all `SensitiveModel`s.

Non-encrypted columns are limited to operational flags a non-clinical front
desk still needs to act safely in an emergency (does this child carry an
EpiPen? is there an anaphylaxis plan on file?) — never the substance.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.accounts.models import Role
from apps.core.fields import EncryptedCharField, EncryptedTextField
from apps.core.models import BaseModel, SensitiveModel, SensitiveSoftDeleteModel
from apps.people.models import Document, Student

_ADMIN_ROLES = frozenset({Role.SUPERADMIN, Role.ADMIN})


class HealthAccessGrant(BaseModel):
    """An explicit, revocable grant letting one staff member view health data.
    SUPERADMIN / ADMIN always qualify and do not need a row here."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="health_access"
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    reason = models.CharField(max_length=255, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "health_access_grant"

    def __str__(self) -> str:
        return f"health access: {self.user} ({'active' if self.active else 'revoked'})"

    @staticmethod
    def user_may_view_health(user) -> bool:
        if not (user and getattr(user, "is_authenticated", False)):
            return False
        if getattr(user, "role", None) in _ADMIN_ROLES:
            return True
        return HealthAccessGrant.objects.filter(user=user, active=True).exists()


class _StudentHealthRecord(SensitiveModel):
    """Shared base: FK to the student + the health-visibility check."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="%(class)ss")

    class Meta:
        abstract = True

    def is_visible_to(self, user) -> bool:
        return HealthAccessGrant.user_may_view_health(user) and self.student.is_visible_to(user)


class HealthProfile(_StudentHealthRecord):
    PII_FIELDS = ("blood_type", "notes")

    student = models.OneToOneField(
        Student, on_delete=models.CASCADE, related_name="health_profile"
    )
    blood_type = EncryptedCharField(blank=True, default="")
    notes = EncryptedTextField(blank=True, default="")
    last_reviewed_at = models.DateField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "health_profile"

    def __str__(self) -> str:
        return f"health profile for {self.student_id}"


class Allergy(_StudentHealthRecord):
    PII_FIELDS = ("allergen", "reaction")

    class Severity(models.TextChoices):
        MILD = "MILD", "Mild"
        MODERATE = "MODERATE", "Moderate"
        SEVERE = "SEVERE", "Severe"
        ANAPHYLAXIS = "ANAPHYLAXIS", "Anaphylaxis"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="allergies")
    allergen = EncryptedCharField()
    reaction = EncryptedTextField(blank=True, default="")
    severity = models.CharField(max_length=12, choices=Severity.choices, default=Severity.MODERATE)
    epipen_required = models.BooleanField(default=False)

    class Meta:
        db_table = "health_allergy"
        verbose_name_plural = "allergies"

    def __str__(self) -> str:
        return f"allergy ({self.severity}) for {self.student_id}"


class Condition(_StudentHealthRecord):
    PII_FIELDS = ("name", "details")

    name = EncryptedCharField()
    details = EncryptedTextField(blank=True, default="")
    diagnosed_on = models.DateField(null=True, blank=True)
    ongoing = models.BooleanField(default=True)

    class Meta:
        db_table = "health_condition"

    def __str__(self) -> str:
        return f"condition for {self.student_id}"


class Medication(_StudentHealthRecord):
    PII_FIELDS = ("name", "dose", "schedule", "prescriber")

    class Route(models.TextChoices):
        ORAL = "ORAL", "Oral"
        TOPICAL = "TOPICAL", "Topical"
        INHALED = "INHALED", "Inhaled"
        INJECTION = "INJECTION", "Injection"
        OTHER = "OTHER", "Other"

    name = EncryptedCharField()
    dose = EncryptedCharField(blank=True, default="")
    schedule = EncryptedCharField(blank=True, default="")
    route = models.CharField(max_length=10, choices=Route.choices, default=Route.ORAL)
    prn = models.BooleanField(default=False, help_text="Given as needed rather than scheduled.")
    prescriber = EncryptedCharField(blank=True, default="")
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "health_medication"

    def __str__(self) -> str:
        return f"medication for {self.student_id}"


class ActionPlan(_StudentHealthRecord, SensitiveSoftDeleteModel):
    PII_FIELDS = ("plan",)

    class Kind(models.TextChoices):
        ANAPHYLAXIS = "ANAPHYLAXIS", "Anaphylaxis"
        ASTHMA = "ASTHMA", "Asthma"
        SEIZURE = "SEIZURE", "Seizure"
        DIABETES = "DIABETES", "Diabetes"
        OTHER = "OTHER", "Other"

    kind = models.CharField(max_length=12, choices=Kind.choices)
    plan = EncryptedTextField()
    effective_from = models.DateField(null=True, blank=True)
    review_by = models.DateField(null=True, blank=True)
    document = models.ForeignKey(
        Document, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "health_action_plan"
        ordering = ["-effective_from"]

    def __str__(self) -> str:
        return f"{self.kind} action plan for {self.student_id}"
