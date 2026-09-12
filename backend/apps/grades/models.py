"""
Assessment schemes and report cards (see docs/DATA_MODEL.md).

Campus supports **rubric + narrative + marks** together — a scheme picks which
apply. Student-level results and report cards carry narrative comments about a
child, so those models are `SensitiveModel` (`EncryptedTextField` for the free
text) with audited reads. A result / report card is only parent-visible once
its parent object is released.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.accounts.models import Role
from apps.core.fields import EncryptedTextField
from apps.core.models import BaseModel, SensitiveModel, SoftDeleteModel
from apps.core.storage import document_storage
from apps.people.models import Group, GroupStaff, Student

_ADMIN_ROLES = frozenset({Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK})
_INSTRUCTOR_ROLES = frozenset({Role.TEACHER, Role.TUTOR})


def _instructor_of(user, group_id) -> bool:
    role = getattr(user, "role", None)
    if role in _ADMIN_ROLES:
        return True
    if role in _INSTRUCTOR_ROLES:
        return GroupStaff.objects.filter(user=user, active=True, group_id=group_id).exists()
    return False


class AssessmentScheme(BaseModel):
    class Kind(models.TextChoices):
        MARKS = "MARKS", "Marks / percentage"
        RUBRIC = "RUBRIC", "Rubric levels"
        NARRATIVE = "NARRATIVE", "Narrative only"
        MIXED = "MIXED", "Rubric + narrative + marks"

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="assessment_schemes")
    term = models.ForeignKey(
        "scheduling.Term", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assessment_schemes",
    )
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.MIXED)

    class Meta:
        db_table = "grades_assessment_scheme"
        ordering = ["group", "name"]

    def __str__(self) -> str:
        return f"{self.group}: {self.name}"

    def is_visible_to(self, user) -> bool:
        return _instructor_of(user, self.group_id)


class RubricCriterion(BaseModel):
    scheme = models.ForeignKey(
        AssessmentScheme, on_delete=models.CASCADE, related_name="criteria"
    )
    label = models.CharField(max_length=150)
    descriptor = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)
    max_level = models.PositiveSmallIntegerField(default=4)

    class Meta:
        db_table = "grades_rubric_criterion"
        ordering = ["scheme", "order"]

    def __str__(self) -> str:
        return self.label


class Assessment(BaseModel):
    scheme = models.ForeignKey(
        AssessmentScheme, on_delete=models.CASCADE, related_name="assessments"
    )
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="assessments")
    title = models.CharField(max_length=200)
    date = models.DateField()
    max_mark = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    released = models.BooleanField(default=False, help_text="Parent-visible once released.")
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "grades_assessment"
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.title} ({self.group})"

    def is_visible_to(self, user) -> bool:
        if _instructor_of(user, self.group_id):
            return True
        if getattr(user, "role", None) == Role.PARENT and self.released:
            return Student.visible_queryset(user).filter(
                enrolments__group_id=self.group_id
            ).exists()
        return False


class AssessmentResult(SensitiveModel):
    PII_FIELDS = ("narrative",)

    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="results"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="assessment_results"
    )
    mark = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    level = models.PositiveSmallIntegerField(null=True, blank=True)
    narrative = EncryptedTextField(blank=True, default="")
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "grades_assessment_result"
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "student"], name="uniq_result_per_student"
            ),
        ]

    def __str__(self) -> str:
        return f"result: {self.student_id} on {self.assessment_id}"

    def is_visible_to(self, user) -> bool:
        if _instructor_of(user, self.assessment.group_id):
            return True
        if getattr(user, "role", None) == Role.PARENT:
            return self.assessment.released and self.student.is_visible_to(user)
        return False


class RubricScore(BaseModel):
    result = models.ForeignKey(
        AssessmentResult, on_delete=models.CASCADE, related_name="rubric_scores"
    )
    criterion = models.ForeignKey(RubricCriterion, on_delete=models.CASCADE, related_name="+")
    level = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "grades_rubric_score"
        constraints = [
            models.UniqueConstraint(
                fields=["result", "criterion"], name="uniq_score_per_criterion"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.criterion_id}: {self.level}"


class GradingScheme(BaseModel):
    """One institution's mapping from a raw mark to what actually prints on
    a report card. Deliberately generic (a name + ordered percentage bands)
    rather than one hardcoded system, because real schools vary enormously —
    a raw percentage, a 4-level provincial scale, a 7-point NCS code, a
    lettered band with no GPA at all, or a full 4.0/5.0 GPA — see
    docs/DATA_MODEL.md and the seeded presets in
    0005_grading_scheme_presets.py for real, sourced examples of each shape.
    Exactly one scheme is ever `is_active` at a time — see `activate()`.
    """

    name = models.CharField(max_length=150)
    description = models.CharField(max_length=255, blank=True)
    uses_gpa = models.BooleanField(
        default=False,
        help_text="If on, a cumulative GPA is computed and printed on report cards.",
    )
    gpa_scale = models.DecimalField(
        max_digits=3, decimal_places=2, null=True, blank=True,
        help_text="e.g. 4.00 or 5.00 - documentation only, bands carry the real points.",
    )
    is_active = models.BooleanField(default=False)

    class Meta:
        db_table = "grades_grading_scheme"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @classmethod
    def active(cls) -> GradingScheme | None:
        return cls.objects.filter(is_active=True).prefetch_related("bands").first()

    def activate(self) -> None:
        """Exactly one scheme is active institution-wide - not enforced by a
        DB constraint (a plain bool, like AcademicYear.is_current), so this
        is the one path that should ever flip it."""
        from django.db import transaction

        with transaction.atomic():
            GradingScheme.objects.exclude(pk=self.pk).update(is_active=False)
            self.is_active = True
            self.save(update_fields=["is_active", "updated_at"])

    def band_for(self, percent) -> GradeBand | None:
        if percent is None:
            return None
        return self.bands.filter(min_percent__lte=percent, max_percent__gte=percent).first()


class GradeBand(BaseModel):
    """One row of a GradingScheme: a percentage window mapped to whatever
    the school actually prints - a letter, a level number, a word."""

    scheme = models.ForeignKey(GradingScheme, on_delete=models.CASCADE, related_name="bands")
    label = models.CharField(
        max_length=30, help_text="What prints on the report card: A, Level 4, 7, Distinction…"
    )
    min_percent = models.DecimalField(max_digits=5, decimal_places=2)
    max_percent = models.DecimalField(max_digits=5, decimal_places=2)
    gpa_points = models.DecimalField(
        max_digits=3, decimal_places=2, null=True, blank=True,
        help_text="Only meaningful when the scheme uses_gpa.",
    )
    description = models.CharField(max_length=150, blank=True)
    order = models.PositiveIntegerField(default=1, help_text="Display order, highest band first.")

    class Meta:
        db_table = "grades_grade_band"
        ordering = ["scheme", "order"]
        constraints = [
            models.UniqueConstraint(fields=["scheme", "label"], name="uniq_band_label_per_scheme"),
        ]

    def __str__(self) -> str:
        return f"{self.scheme.name}: {self.label} ({self.min_percent}-{self.max_percent}%)"


class ReportCard(SensitiveModel, SoftDeleteModel):
    PII_FIELDS = ("summary_narrative",)

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        FINALIZED = "FINALIZED", "Finalized"
        RELEASED = "RELEASED", "Released to guardians"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="report_cards")
    term = models.ForeignKey(
        "scheduling.Term", on_delete=models.PROTECT, related_name="report_cards"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    summary_narrative = EncryptedTextField(blank=True, default="")
    document = models.FileField(
        upload_to="report-cards/%Y/", storage=document_storage, blank=True
    )
    grading_scheme = models.ForeignKey(
        GradingScheme, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="The scheme active when this card was generated - a historical snapshot, "
                   "not a live pointer, so a later policy change doesn't rewrite old cards.",
    )
    cumulative_gpa = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
        help_text="Computed at generation time from entries whose mark maps to a "
                   "GPA-bearing band. Unweighted (Campus doesn't model credit-hours).",
    )
    generated_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "grades_report_card"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "term"], name="uniq_report_card_per_term",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return f"report card: {self.student_id} {self.term_id} ({self.status})"

    def is_visible_to(self, user) -> bool:
        role = getattr(user, "role", None)
        if role in _ADMIN_ROLES:
            return True
        if role in _INSTRUCTOR_ROLES:
            return self.student.is_visible_to(user)
        if role == Role.PARENT:
            return self.status == self.Status.RELEASED and self.student.is_visible_to(user)
        return False


class ReportCardEntry(SensitiveModel):
    PII_FIELDS = ("comment",)

    report_card = models.ForeignKey(
        ReportCard, on_delete=models.CASCADE, related_name="entries"
    )
    subject = models.CharField(max_length=150)  # group name / course / learning area
    group = models.ForeignKey(
        Group, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    mark = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    level = models.PositiveSmallIntegerField(null=True, blank=True)
    comment = EncryptedTextField(blank=True, default="")
    order = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "grades_report_card_entry"
        ordering = ["report_card", "order"]

    def __str__(self) -> str:
        return f"{self.subject} on {self.report_card_id}"

    def is_visible_to(self, user) -> bool:
        return self.report_card.is_visible_to(user)
