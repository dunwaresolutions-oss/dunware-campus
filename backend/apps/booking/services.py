"""
Slot generation, booking, cancellation with waitlist promotion, and ICS export.
"""
from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record

from .models import AvailabilityWindow, Booking, Offering, Slot


class BookingError(Exception):
    """A booking could not be made or cancelled as asked."""


def _site_closure_dates(start: dt.date, end: dt.date) -> set[dt.date]:
    from apps.scheduling.models import Closure

    days: set[dt.date] = set()
    for c in Closure.objects.filter(group__isnull=True, end_date__gte=start, start_date__lte=end):
        d = c.start_date
        while d <= c.end_date:
            days.add(d)
            d += dt.timedelta(days=1)
    return days


def generate_slots(
    offering: Offering, *, from_date: dt.date, to_date: dt.date, actor=None
) -> dict:
    windows = list(
        AvailabilityWindow.objects.filter(offering=offering, active=True)
        .filter(valid_from__lte=to_date, valid_to__gte=from_date)
    )
    closed = _site_closure_dates(from_date, to_date)
    existing = {
        (s.window_id, s.starts_at)
        for s in Slot.objects.filter(offering=offering, window__in=windows)
    }
    created = skipped_closed = skipped_existing = 0
    new_slots = []
    dur = dt.timedelta(minutes=offering.duration_minutes)

    for w in windows:
        day = max(from_date, w.valid_from)
        day += dt.timedelta(days=(w.weekday - day.weekday()) % 7)
        end = min(to_date, w.valid_to)
        while day <= end:
            if day in closed:
                skipped_closed += 1
                day += dt.timedelta(days=7)
                continue
            cursor = timezone.make_aware(dt.datetime.combine(day, w.start_time))
            window_end = timezone.make_aware(dt.datetime.combine(day, w.end_time))
            while cursor + dur <= window_end:
                if (w.id, cursor) in existing:
                    skipped_existing += 1
                else:
                    new_slots.append(Slot(
                        offering=offering, window=w, starts_at=cursor, ends_at=cursor + dur,
                        capacity=offering.capacity_per_slot,
                    ))
                cursor += dur
            day += dt.timedelta(days=7)

    if new_slots:
        Slot.objects.bulk_create(new_slots)
        created = len(new_slots)
        record(AuditAction.CREATE, offering, summary=f"generated {created} booking slots",
               actor=actor)
    return {"created": created, "skipped_closed": skipped_closed,
            "skipped_existing": skipped_existing}


@transaction.atomic
def book(*, slot: Slot, student, by=None) -> Booking:
    slot = Slot.objects.select_for_update().get(pk=slot.pk)
    if slot.status == Slot.Status.CANCELLED:
        raise BookingError("That slot has been cancelled.")

    existing = slot.bookings.filter(student=student).exclude(
        status=Booking.Status.CANCELLED
    ).first()
    if existing is not None:
        raise BookingError("This student already has a booking for that slot.")

    if slot.seats_left > 0:
        booking = Booking.objects.create(
            slot=slot, student=student, booked_by=by, status=Booking.Status.CONFIRMED
        )
    else:
        last = slot.bookings.filter(status=Booking.Status.WAITLISTED).order_by(
            "-waitlist_position"
        ).first()
        pos = (last.waitlist_position + 1) if last and last.waitlist_position else 1
        booking = Booking.objects.create(
            slot=slot, student=student, booked_by=by,
            status=Booking.Status.WAITLISTED, waitlist_position=pos,
        )
    slot.refresh_status()
    record(AuditAction.CREATE, booking, summary=f"booked ({booking.status})", actor=by)
    return booking


@transaction.atomic
def cancel_booking(*, booking: Booking, by=None, note: str = "", enforce_cutoff: bool = True):
    if booking.status == Booking.Status.CANCELLED:
        return booking
    slot = Slot.objects.select_for_update().get(pk=booking.slot_id)
    cutoff = slot.starts_at - dt.timedelta(hours=slot.offering.cancellation_hours)
    if enforce_cutoff and timezone.now() > cutoff:
        raise BookingError(
            "Too late to cancel this booking online; contact the office."
        )

    was_confirmed = booking.status == Booking.Status.CONFIRMED
    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.cancelled_by = by if getattr(by, "pk", None) else None
    booking.cancellation_note = note[:255]
    booking.waitlist_position = None
    booking.save()
    record(AuditAction.UPDATE, booking, summary="booking cancelled", actor=by)

    promoted = None
    if was_confirmed:
        promoted = slot.bookings.filter(status=Booking.Status.WAITLISTED).order_by(
            "waitlist_position", "created_at"
        ).first()
        if promoted is not None:
            promoted.status = Booking.Status.CONFIRMED
            promoted.waitlist_position = None
            promoted.save(update_fields=["status", "waitlist_position", "updated_at"])
            record(AuditAction.UPDATE, promoted,
                   summary="promoted from waitlist to confirmed", actor=by)
    slot.refresh_status()
    return booking, promoted


def _ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
        .replace("\n", "\\n")
    )


def bookings_to_ics(bookings, *, calendar_name: str = "Campus bookings") -> str:
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Dunware//Campus//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(calendar_name)}",
    ]
    stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    for b in bookings:
        slot = b.slot
        lines += [
            "BEGIN:VEVENT",
            f"UID:booking-{b.pk}@campus",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{slot.starts_at.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{slot.ends_at.strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{_ics_escape(slot.offering.title)} — {_ics_escape(b.student.display_name)}",
            f"STATUS:{'CONFIRMED' if b.status == b.Status.CONFIRMED else 'TENTATIVE'}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
