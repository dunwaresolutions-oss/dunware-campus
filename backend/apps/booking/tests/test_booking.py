from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.booking.models import AvailabilityWindow, Booking, Offering, Slot
from apps.booking.services import (
    BookingError,
    book,
    bookings_to_ics,
    cancel_booking,
    generate_slots,
)
from apps.people.tests.factories import link_guardian, make_student
from apps.scheduling.models import Closure

pytestmark = pytest.mark.django_db


def _offering(**kw) -> Offering:
    kw.setdefault("title", "Chess club")
    kw.setdefault("duration_minutes", 60)
    kw.setdefault("capacity_per_slot", 2)
    kw.setdefault("cancellation_hours", 24)
    return Offering.objects.create(**kw)


def _slot(offering, when=None, capacity=None) -> Slot:
    when = when or (timezone.now() + dt.timedelta(days=3))
    return Slot.objects.create(
        offering=offering, starts_at=when,
        ends_at=when + dt.timedelta(minutes=offering.duration_minutes),
        capacity=capacity or offering.capacity_per_slot,
    )


def test_generate_slots_from_windows_idempotent_and_skips_closures():
    offering = _offering(duration_minutes=60)
    AvailabilityWindow.objects.create(
        offering=offering, weekday=0, start_time=dt.time(15, 0), end_time=dt.time(17, 0),
        valid_from=dt.date(2026, 9, 1), valid_to=dt.date(2026, 9, 30),
    )
    # Mondays in Sept 2026: 7, 14, 21, 28 -> 2 hourly slots each = 8
    Closure.objects.create(start_date=dt.date(2026, 9, 14), end_date=dt.date(2026, 9, 14),
                           reason="PD day")

    first = generate_slots(offering, from_date=dt.date(2026, 9, 1), to_date=dt.date(2026, 9, 30))
    assert first["created"] == 6  # 3 mondays * 2 slots
    assert first["skipped_closed"] == 1

    again = generate_slots(offering, from_date=dt.date(2026, 9, 1), to_date=dt.date(2026, 9, 30))
    assert again["created"] == 0
    assert again["skipped_existing"] == 6


def test_booking_fills_then_waitlists():
    offering = _offering(capacity_per_slot=2)
    slot = _slot(offering, capacity=2)
    a, b, c = make_student(), make_student(), make_student()

    b1 = book(slot=slot, student=a)
    b2 = book(slot=slot, student=b)
    b3 = book(slot=slot, student=c)

    assert b1.status == b2.status == Booking.Status.CONFIRMED
    assert b3.status == Booking.Status.WAITLISTED
    assert b3.waitlist_position == 1
    slot.refresh_from_db()
    assert slot.status == Slot.Status.FULL


def test_double_booking_the_same_student_is_rejected():
    offering = _offering(capacity_per_slot=3)
    slot = _slot(offering)
    kid = make_student()
    book(slot=slot, student=kid)
    with pytest.raises(BookingError):
        book(slot=slot, student=kid)


def test_cancelling_a_confirmed_booking_promotes_the_waitlist():
    offering = _offering(capacity_per_slot=1)
    slot = _slot(offering, capacity=1)
    a, b = make_student(), make_student()
    confirmed = book(slot=slot, student=a)
    waitlisted = book(slot=slot, student=b)
    assert waitlisted.status == Booking.Status.WAITLISTED

    _cancelled, promoted = cancel_booking(booking=confirmed, enforce_cutoff=False)
    assert promoted is not None and promoted.pk == waitlisted.pk
    promoted.refresh_from_db()
    assert promoted.status == Booking.Status.CONFIRMED
    assert promoted.waitlist_position is None
    slot.refresh_from_db()
    assert slot.status == Slot.Status.FULL


def test_cancellation_cutoff_blocks_a_late_online_cancel():
    offering = _offering(cancellation_hours=24)
    slot = _slot(offering, when=timezone.now() + dt.timedelta(hours=2))  # inside the window
    kid = make_student()
    booking = book(slot=slot, student=kid)
    with pytest.raises(BookingError):
        cancel_booking(booking=booking, enforce_cutoff=True)
    # staff override
    out = cancel_booking(booking=booking, enforce_cutoff=False)
    assert out[0].status == Booking.Status.CANCELLED


def test_api_parent_books_own_child_only(auth_client, make_user):
    offering = _offering(capacity_per_slot=2)
    slot = _slot(offering)
    mine, theirs = make_student(), make_student()
    parent = make_user(username="bp", role="PARENT")
    link_guardian(mine, user=parent)

    client = auth_client(parent)
    ok = client.post("/api/bookings/", {"slot": str(slot.pk), "student": str(mine.pk)},
                     format="json")
    assert ok.status_code == 201
    assert ok.data["status"] == "CONFIRMED"

    denied = client.post("/api/bookings/", {"slot": str(slot.pk), "student": str(theirs.pk)},
                         format="json")
    assert denied.status_code == 403


def test_api_ics_export_lists_the_users_bookings(auth_client, make_user):
    offering = _offering(capacity_per_slot=2)
    slot = _slot(offering)
    kid = make_student(first_name="Ivy", last_name="Ng")
    parent = make_user(username="ics", role="PARENT")
    link_guardian(kid, user=parent)
    book(slot=slot, student=kid, by=parent)

    client = auth_client(parent)
    resp = client.get("/api/bookings/ics/")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/calendar")
    text = resp.content.decode()
    assert text.startswith("BEGIN:VCALENDAR")
    assert "BEGIN:VEVENT" in text
    assert "Chess club" in text and "Ivy Ng" in text


def test_ics_helper_escapes_and_wraps():
    kid = make_student()
    offering = _offering(title="Robotics, Level 1")
    slot = _slot(offering)
    b = book(slot=slot, student=kid)
    ics = bookings_to_ics([b])
    assert "Robotics\\, Level 1" in ics
    assert ics.endswith("END:VCALENDAR\r\n")
