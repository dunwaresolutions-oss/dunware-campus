"""
Calendars, rosters, recurring session templates, closures
(see docs/DATA_MODEL.md).

`AcademicYear → Term` carries the configurable term model (semester / trimester
/ quarter / rolling-continuous / year-round). A `SessionTemplate` is a weekly
recurring meeting for a group; `generate_occurrences()` expands it across a
date range, skipping `Closure`s, into concrete `SessionOccurrence` rows that
attendance and lessons hang off. Rosters are read from `registration.Enrolment`
— never duplicated here.

Nothing in this app is PII, so no encryption; access is still staff + MFA and
instructors are scoped to the groups they staff.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.people.models import Group


class Room(BaseModel):
    class Kind(models.TextChoices):
        CLASSROOM = "CLASSROOM", "Classroom"
        GYM = "GYM", "Gym / activity hall"
        OUTDOOR = "OUTDOOR", "Outdoor space"
        RESOURCE = "RESOURCE", "Shared resource"

    name = models.CharField(max_length=120, unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CLASSROOM)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "scheduling_room"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class AcademicYear(BaseModel):
    name = models.CharField(max_length=40, unique=True)  # "2026–2027"
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        db_table = "scheduling_academic_year"
        ordering = ["-start_date"]

    def __str__(self) -> str:
        return self.name


class Term(BaseModel):
    class Kind(models.TextChoices):
        SEMESTER = "SEMESTER", "Semester"
        TRIMESTER = "TRIMESTER", "Trimester"
        QUARTER = "QUARTER", "Quarter"
        ROLLING = "ROLLING", "Rolling / continuous"
        YEAR_ROUND = "YEAR_ROUND", "Year-round"

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="terms"
    )
    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.SEMESTER)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        db_table = "scheduling_term"
        ordering = ["start_date"]
        constraints = [
            models.UniqueConstraint(fields=["academic_year", "name"], name="uniq_term_per_year"),
        ]

    def __str__(self) -> str:
        return f"{self.academic_year.name} · {self.name}"

    def covers(self, day) -> bool:
        return self.start_date <= day <= self.end_date


class Closure(BaseModel):
    """A day (or span) with no sessions. Site-wide when `group` is null."""

    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=200)
    group = models.ForeignKey(
        Group, null=True, blank=True, on_delete=models.CASCADE, related_name="closures"
    )

    class Meta:
        db_table = "scheduling_closure"
        ordering = ["start_date"]

    def __str__(self) -> str:
        where = self.group.name if self.group_id else "site-wide"
        return f"closure {self.start_date}–{self.end_date} ({where}): {self.reason}"

    def blocks(self, day, group_id=None) -> bool:
        if not (self.start_date <= day <= self.end_date):
            return False
        return self.group_id is None or self.group_id == group_id


class SessionTemplate(BaseModel):
    """A weekly recurring meeting for a group within a term."""

    class Weekday(models.IntegerChoices):
        MON = 0, "Monday"
        TUE = 1, "Tuesday"
        WED = 2, "Wednesday"
        THU = 3, "Thursday"
        FRI = 4, "Friday"
        SAT = 5, "Saturday"
        SUN = 6, "Sunday"

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="session_templates")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="session_templates")
    room = models.ForeignKey(
        Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="session_templates"
    )
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="session_templates",
    )
    weekday = models.IntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    title = models.CharField(max_length=120, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "scheduling_session_template"
        ordering = ["weekday", "start_time"]

    def __str__(self) -> str:
        return f"{self.group} {self.get_weekday_display()} {self.start_time:%H:%M}"


class SessionOccurrence(BaseModel):
    """A concrete dated meeting. Generated from a template or added ad hoc."""

    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        CANCELLED = "CANCELLED", "Cancelled"

    template = models.ForeignKey(
        SessionTemplate, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="occurrences",
    )
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="session_occurrences")
    room = models.ForeignKey(
        Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="session_occurrences"
    )
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="session_occurrences",
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    title = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    cancelled_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "scheduling_session_occurrence"
        ordering = ["date", "start_time"]
        indexes = [
            models.Index(fields=["group", "date"]),
            models.Index(fields=["date", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "date"],
                condition=models.Q(template__isnull=False),
                name="uniq_occurrence_per_template_date",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.group} on {self.date} {self.start_time:%H:%M} ({self.status})"

    def roster(self):
        """Students actively enrolled in the group on this date."""
        from apps.registration.models import Enrolment

        return Enrolment.objects.filter(
            group_id=self.group_id, status=Enrolment.Status.ACTIVE, start_date__lte=self.date,
        ).exclude(end_date__lt=self.date).select_related("student")

    def is_visible_to(self, user) -> bool:
        from apps.accounts.models import Role
        from apps.people.models import GroupStaff

        role = getattr(user, "role", None)
        if role in {Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK}:
            return True
        if role in {Role.TEACHER, Role.TUTOR}:
            return GroupStaff.objects.filter(
                user=user, active=True, group_id=self.group_id
            ).exists()
        return False
