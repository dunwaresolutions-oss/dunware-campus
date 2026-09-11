from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.booking.models import Offering, Slot
from apps.booking.services import book
from apps.people.tests.factories import make_student

pytestmark = pytest.mark.django_db


def _offering(**kw) -> Offering:
    kw.setdefault("duration_minutes", 60)
    kw.setdefault("capacity_per_slot", 2)
    kw.setdefault("cancellation_hours", 24)
    return Offering.objects.create(**kw)


def _slot(offering, **kw) -> Slot:
    when = kw.pop("when", timezone.now() + dt.timedelta(days=3))
    return Slot.objects.create(
        offering=offering, starts_at=when,
        ends_at=when + dt.timedelta(minutes=offering.duration_minutes),
        capacity=kw.pop("capacity", offering.capacity_per_slot),
    )


def test_offerings_search_by_title(auth_client, admin_user):
    _offering(title="Chess club")
    _offering(title="Piano lessons")
    client = auth_client(admin_user)
    resp = client.get("/api/offerings/?q=chess")
    titles = {row["title"] for row in resp.data["results"]}
    assert titles == {"Chess club"}


def test_bookings_search_by_student_or_offering(auth_client, admin_user):
    offering = _offering(title="Chess club")
    slot = _slot(offering)
    findme = make_student(first_name="Zelda", last_name="Nohansen")
    other = make_student(first_name="Bowser", last_name="Koopa")
    book(slot=slot, student=findme)
    book(slot=slot, student=other)

    client = auth_client(admin_user)
    resp = client.get("/api/bookings/?q=Zelda")
    names = {row["student_name"] for row in resp.data["results"]}
    assert names == {"Zelda Nohansen"}

    resp = client.get("/api/bookings/?q=Chess")
    assert len(resp.data["results"]) == 2
