"""The console-wide /api/search/ endpoint."""
from __future__ import annotations

import pytest

from apps.people.models import Guardian, GuardianLink
from apps.people.tests.factories import make_group, make_student

pytestmark = pytest.mark.django_db


def _hits(resp, group_title):
    for g in resp.data["groups"]:
        if g["title"] == group_title:
            return g["items"]
    return []


def test_finds_students_guardians_and_groups(auth_client, admin_user):
    kid = make_student(first_name="Beatrix", last_name="Sunderland")
    make_student(first_name="Nolan", last_name="Frost")
    grp = make_group(name="Sunbeam Room")
    g = Guardian.objects.create(first_name="Petra", last_name="Sunderland",
                                email="petra@example.test")
    GuardianLink.objects.create(student=kid, guardian=g, relationship="MOTHER")

    client = auth_client(admin_user)
    r = client.get("/api/search/?q=sunder")
    assert r.status_code == 200
    s = _hits(r, "Students")
    assert any(h["id"] == str(kid.pk) for h in s)
    assert all("Nolan" not in h["label"] for h in s)
    assert any(h["id"] == str(g.pk) for h in _hits(r, "Guardians"))

    r2 = client.get("/api/search/?q=sunbeam")
    assert any(h["id"] == str(grp.pk) for h in _hits(r2, "Groups"))


def test_short_query_returns_nothing(auth_client, admin_user):
    make_student(first_name="Ada", last_name="Ng")
    r = auth_client(admin_user).get("/api/search/?q=a")
    assert r.status_code == 200
    assert r.data["groups"] == []


def test_instructor_only_sees_their_students(auth_client, staff, make_user):
    from apps.people.tests.factories import assign_staff, enrol

    mine = make_group(name="My Class")
    theirs = make_group(name="Other Class")
    assign_staff(mine, staff)
    a = make_student(first_name="Zeb", last_name="Marlow")
    b = make_student(first_name="Zeb", last_name="Corrin")
    enrol(a, mine)
    enrol(b, theirs)

    r = auth_client(staff).get("/api/search/?q=zeb")
    ids = {h["id"] for h in _hits(r, "Students")}
    assert str(a.pk) in ids and str(b.pk) not in ids
    # instructors don't get the Staff group at all
    assert _hits(r, "Staff") == []


def test_portal_user_gets_nothing(auth_client, parent):
    make_student(first_name="Search", last_name="Target")
    r = auth_client(parent).get("/api/search/?q=target")
    assert r.status_code in (200, 403)
    if r.status_code == 200:
        assert r.data["groups"] == []
