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


def test_finds_a_student_by_full_first_and_last_name(auth_client, admin_user):
    """Damien, 2026-09-16: an issued invoice existed for "Uriah Oliver" but
    searching that exact name found nothing. Root cause: first_name and
    last_name are separate fields, so a single icontains("Uriah Oliver")
    check against either one alone can never match - the query has to be
    split into words and each word matched against SOME field."""
    make_student(first_name="Uriah", last_name="Oliver")
    make_student(first_name="Someone", last_name="Else")

    client = auth_client(admin_user)
    r = client.get("/api/search/?q=Uriah+Oliver")
    assert r.status_code == 200
    hits = _hits(r, "Students")
    assert any(h["label"] == "Uriah Oliver" for h in hits)
    assert len(hits) == 1

    # order/case shouldn't matter, and it still works as a bare single word
    r2 = client.get("/api/search/?q=oliver uriah")
    assert any(h["label"] == "Uriah Oliver" for h in _hits(r2, "Students"))
    r3 = client.get("/api/search/?q=uriah")
    assert any(h["label"] == "Uriah Oliver" for h in _hits(r3, "Students"))


def test_full_name_search_does_not_cross_match_unrelated_people(auth_client, admin_user):
    """"Uriah Oliver" must not match a student named "Uriah Adderley" and a
    guardian named "Oliver Bain" just because each word matches someone -
    the AND is per-person (per queryset row), not just "both words appear
    somewhere in the table.\""""
    make_student(first_name="Uriah", last_name="Adderley")
    make_student(first_name="Marcus", last_name="Oliver")

    client = auth_client(admin_user)
    r = client.get("/api/search/?q=Uriah+Oliver")
    assert r.status_code == 200
    assert _hits(r, "Students") == []


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
