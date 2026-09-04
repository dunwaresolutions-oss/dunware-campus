"""
Booking — tutors and extra-curriculars (see docs/DATA_MODEL.md).

`Offering` is a bookable service; `AvailabilityWindow`s describe when it runs;
`generate_slots()` expands those into concrete `Slot`s with a capacity; a
`Booking` puts one student in one slot, or on its waitlist. Cancelling a
confirmed booking promotes the next person on the waitlist.

`price_cents` is a **placeholder** — no money changes hands in v1; the field
is the hook Phase 7 (`billing`) reads. `Booking` carries "which child does
which activity", so it is a `SensitiveModel` with audited reads.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.accounts.models import Role
from apps.core.models import BaseModel, SensitiveModel
from apps.people.models import Student

_ADMIN_ROLES = frozenset({Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK})


class Offering(BaseModel):
    class Kind(models.TextChoices):
        TUTORING = "TUTORING", "Tutoring"
        MUSIC = "MUSIC", "Music"
        SPORT = "SPORT", "Sport"
        CLUB = "CLUB", "Club / extra-curricular"
        OTHER = "OTHER", "Other"

    title = models.CharField(max_length=150)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CLUB)
    description = models.TextField(blank=True)
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="booking_offerings",
    )
    room = models.ForeignKey(
        "scheduling.Room", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="booking_offerings",
    )
    duration_minutes = models.PositiveIntegerField(default=30)
    capacity_per_slot = models.PositiveIntegerField(default=1)
    cancellation_hours = models.PositiveIntegerField(
        default=24, help_text="Free-cancellation cutoff before a slot starts."
    )
    price_cents = models.PositiveIntegerField(
        null=True, blank=True, help_text="Placeholder — Phase 7 billing hook; no charge in v1."
    )
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "booking_offering"
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class AvailabilityWindow(BaseModel):
    class Weekday(models.IntegerChoices):
        MON = 0, "Monday"
        TUE = 1, "Tuesday"
        WED = 2, "Wednesday"
        THU = 3, "Thursday"
        FRI = 4, "Friday"
        SAT = 5, "Saturday"
        SUN = 6, "Sunday"

    offering = models.ForeignKey(
        Offering, on_delete=models.CASCADE, related_name="availability_windows"
    )
    weekday = models.IntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    valid_from = models.DateField()
    valid_to = models.DateField()
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "booking_availability_window"
        ordering = ["weekday", "start_time"]

    def __str__(self) -> str:
        return f"{self.offering} {self.get_weekday_display()} {self.start_time:%H:%M}"


class Slot(BaseModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        FULL = "FULL", "Full"
        CANCELLED = "CANCELLED", "Cancelled"

    offering = models.ForeignKey(Offering, on_delete=models.CASCADE, related_name="slots")
    window = models.ForeignKey(
        AvailabilityWindow, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="slots",
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    capacity = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.OPEN)

    class Meta:
        db_table = "booking_slot"
        ordering = ["starts_at"]
        indexes = [models.Index(fields=["offering", "starts_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["window", "starts_at"],
                condition=models.Q(window__isnull=False),
                name="uniq_slot_per_window_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.offering} @ {self.starts_at:%Y-%m-%d %H:%M}"

    @property
    def confirmed_count(self) -> int:
        return self.bookings.filter(status=Booking.Status.CONFIRMED).count()

    @property
    def seats_left(self) -> int:
        return max(self.capacity - self.confirmed_count, 0)

    def refresh_status(self):
        if self.status == self.Status.CANCELLED:
            return
        new = self.Status.FULL if self.seats_left == 0 else self.Status.OPEN
        if new != self.status:
            self.status = new
            self.save(update_fields=["status"])


class Booking(SensitiveModel):
    PII_FIELDS = ("cancellation_note",)

    class Status(models.TextChoices):
        CONFIRMED = "CONFIRMED", "Confirmed"
        WAITLISTED = "WAITLISTED", "Waitlisted"
        CANCELLED = "CANCELLED", "Cancelled"
        ATTENDED = "ATTENDED", "Attended"
        NO_SHOW = "NO_SHOW", "No-show"

    slot = models.ForeignKey(Slot, on_delete=models.CASCADE, related_name="bookings")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="bookings")
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CONFIRMED)
    waitlist_position = models.PositiveIntegerField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    cancellation_note = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "booking_booking"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["slot", "status"]),
            models.Index(fields=["student", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["slot", "student"],
                condition=~models.Q(status="CANCELLED"),
                name="uniq_active_booking_per_slot",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student_id} → {self.slot_id} ({self.status})"

    @property
    def is_active(self) -> bool:
        return self.status in (self.Status.CONFIRMED, self.Status.WAITLISTED)

    def is_visible_to(self, user) -> bool:
        role = getattr(user, "role", None)
        if role in _ADMIN_ROLES:
            return True
        if role in (Role.TEACHER, Role.TUTOR):
            if self.slot.offering.provider_id == user.pk:
                return True
            return self.student.is_visible_to(user)
        if role == Role.PARENT:
            return self.student.is_visible_to(user)
        return False
