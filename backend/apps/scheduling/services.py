"""
Expanding recurring templates into concrete dated sessions.

`generate_occurrences(template, from_date, to_date)` walks every date in the
range that matches the template's weekday, skips any `Closure` covering that
date for the group (or site-wide), and creates a `SessionOccurrence` — unless
one already exists for that (template, date), so it is safe to re-run after
adding a closure or extending a term.
"""
from __future__ import annotations

import datetime as dt

from apps.audit.models import AuditAction
from apps.audit.services import record

from .models import Closure, SessionOccurrence, SessionTemplate


def _dates(start: dt.date, end: dt.date, weekday: int):
    day = start
    # advance to the first matching weekday
    offset = (weekday - day.weekday()) % 7
    day = day + dt.timedelta(days=offset)
    while day <= end:
        yield day
        day += dt.timedelta(days=7)


def generate_occurrences(
    template: SessionTemplate, *, from_date: dt.date | None = None,
    to_date: dt.date | None = None, actor=None,
) -> dict:
    if not template.active:
        return {"created": 0, "skipped_closed": 0, "skipped_existing": 0, "reason": "inactive"}

    term = template.term
    start = max(from_date or term.start_date, term.start_date)
    end = min(to_date or term.end_date, term.end_date)

    closures = list(Closure.objects.filter(end_date__gte=start, start_date__lte=end))
    existing = set(
        SessionOccurrence.objects.filter(template=template)
        .values_list("date", flat=True)
    )

    created = skipped_closed = skipped_existing = 0
    to_make = []
    for day in _dates(start, end, template.weekday):
        if day in existing:
            skipped_existing += 1
            continue
        if any(c.blocks(day, template.group_id) for c in closures):
            skipped_closed += 1
            continue
        to_make.append(SessionOccurrence(
            template=template, group=template.group, room=template.room,
            staff=template.staff, date=day, start_time=template.start_time,
            end_time=template.end_time, title=template.title,
        ))

    if to_make:
        SessionOccurrence.objects.bulk_create(to_make)
        created = len(to_make)
        record(
            AuditAction.CREATE, template,
            summary=f"generated {created} session occurrences", actor=actor,
            extra={"from": str(start), "to": str(end)},
        )

    return {
        "created": created,
        "skipped_closed": skipped_closed,
        "skipped_existing": skipped_existing,
    }
