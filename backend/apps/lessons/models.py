"""
Curriculum units and lesson plans (see docs/DATA_MODEL.md).

Not PII — teaching material, not people. Access is still staff + MFA, and
instructors are scoped to the groups they staff. Parent visibility of a
published plan is a Phase-6 portal concern.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.accounts.models import Role
from apps.core.models import BaseModel, SoftDeleteModel
from apps.people.models import Group, GroupStaff

_ADMIN_ROLES = {Role.SUPERADMIN, Role.ADMIN}


def _instructor_can_touch_group(user, group_id) -> bool:
    role = getattr(user, "role", None)
    if role in _ADMIN_ROLES:
        return True
    if role in {Role.TEACHER, Role.TUTOR}:
        return GroupStaff.objects.filter(user=user, active=True, group_id=group_id).exists()
    return False


class CurriculumUnit(BaseModel):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="curriculum_units")
    term = models.ForeignKey(
        "scheduling.Term", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="curriculum_units",
    )
    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True)
    sequence = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "lessons_curriculum_unit"
        ordering = ["group", "sequence"]

    def __str__(self) -> str:
        return f"{self.group}: {self.title}"

    def is_visible_to(self, user) -> bool:
        return _instructor_can_touch_group(user, self.group_id)


class LessonPlan(SoftDeleteModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="lesson_plans")
    unit = models.ForeignKey(
        CurriculumUnit, null=True, blank=True, on_delete=models.SET_NULL, related_name="lessons"
    )
    date = models.DateField()
    title = models.CharField(max_length=200)
    objectives = models.TextField(blank=True)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="lesson_plans"
    )

    class Meta:
        db_table = "lessons_lesson_plan"
        ordering = ["-date"]
        indexes = [models.Index(fields=["group", "date"])]

    def __str__(self) -> str:
        return f"{self.date} {self.title} ({self.status})"

    def is_visible_to(self, user) -> bool:
        return _instructor_can_touch_group(user, self.group_id)


class LessonResource(BaseModel):
    """A link, file, or note. Always for one **group** — usually attached to
    one dated lesson within it, but a resource that applies to the group
    generally (a standing reading list, a permission slip template) can skip
    ``lesson`` and hang directly off the group instead."""

    class Kind(models.TextChoices):
        LINK = "LINK", "Link"
        FILE = "FILE", "File"
        NOTE = "NOTE", "Note"

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="lesson_resources",
        help_text="Who this is for. Auto-filled from the lesson plan when one is set.",
    )
    lesson = models.ForeignKey(
        LessonPlan,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="resources",
        help_text="Optional — leave blank for a resource that isn't tied to one dated lesson.",
    )
    kind = models.CharField(max_length=6, choices=Kind.choices, default=Kind.LINK)
    title = models.CharField(max_length=200)
    url = models.URLField(blank=True)
    file = models.FileField(upload_to="lesson-resources/%Y/%m/", blank=True)
    body = models.TextField(blank=True)

    class Meta:
        db_table = "lessons_lesson_resource"
        ordering = ["title"]
        indexes = [models.Index(fields=["group"])]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if self.lesson_id and not self.group_id:
            self.group_id = self.lesson.group_id
        super().save(*args, **kwargs)

    def is_visible_to(self, user) -> bool:
        return _instructor_can_touch_group(user, self.group_id)
