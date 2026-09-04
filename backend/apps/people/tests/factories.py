"""Tiny helpers for building people/registration graphs in tests."""
from __future__ import annotations

import datetime as dt

from django.utils import timezone

from apps.people.models import (
    Group,
    GroupStaff,
    Guardian,
    GuardianLink,
    Student,
)
from apps.registration.models import Enrolment

_counter = {"n": 0}


def _n() -> int:
    _counter["n"] += 1
    return _counter["n"]


def make_group(**kw) -> Group:
    kw.setdefault("name", f"Group {_n()}")
    return Group.objects.create(**kw)


def make_student(**kw) -> Student:
    i = _n()
    kw.setdefault("first_name", f"Kid{i}")
    kw.setdefault("last_name", "Test")
    kw.setdefault("date_of_birth", dt.date(2018, 1, 1))
    kw.setdefault("student_number", f"S{900000 + i}")
    kw.setdefault("status", Student.Status.ENROLLED)
    return Student.objects.create(**kw)


def enrol(student, group, **kw) -> Enrolment:
    kw.setdefault("start_date", timezone.localdate())
    return Enrolment.objects.create(student=student, group=group, **kw)


def link_guardian(student, user=None, **kw) -> GuardianLink:
    i = _n()
    guardian = Guardian.objects.create(
        first_name=kw.pop("first_name", f"Guardian{i}"),
        last_name=kw.pop("last_name", "Test"),
        email=kw.pop("email", f"guardian{i}@example.test"),
        user=user,
    )
    kw.setdefault("relationship", GuardianLink.Relationship.PARENT)
    return GuardianLink.objects.create(student=student, guardian=guardian, **kw)


def assign_staff(group, user, **kw) -> GroupStaff:
    kw.setdefault("role", GroupStaff.Role.LEAD)
    return GroupStaff.objects.create(group=group, user=user, **kw)
