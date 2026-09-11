"""IEP — scoping, the child viewsets, the rendered document, and the portal."""
from __future__ import annotations

import pytest

from apps.iep.models import IEP, IEPGoal
from apps.people.tests.factories import (
    assign_staff,
    enrol,
    link_guardian,
    make_group,
    make_student,
)

pytestmark = pytest.mark.django_db

URL = "/api/ieps/"


def _iep(student, **kw):
    kw.setdefault("status", IEP.Status.ACTIVE)
    kw.setdefault("primary_concern", "Reading fluency")
    return IEP.objects.create(student=student, **kw)


def test_front_office_creates_and_lists_an_iep(auth_client, front_desk):
    s = make_student()
    c = auth_client(front_desk)
    r = c.post(URL, {"student": str(s.id), "primary_concern": "Math"}, format="json")
    assert r.status_code == 201
    assert c.get(URL, {"student": str(s.id)}).data["count"] == 1


def test_instructor_sees_only_their_students_ieps(auth_client, staff):
    g = make_group()
    assign_staff(g, staff)
    mine, theirs = make_student(), make_student()
    enrol(mine, g)
    _iep(mine)
    _iep(theirs)
    data = auth_client(staff).get(URL).data
    assert data["count"] == 1
    assert str(data["results"][0]["student"]) == str(mine.id)


def test_status_filter(auth_client, admin_user):
    s = make_student()
    _iep(s, status=IEP.Status.ACTIVE)
    _iep(s, status=IEP.Status.ARCHIVED)
    c = auth_client(admin_user)
    assert c.get(URL, {"student": str(s.id), "status": "ACTIVE"}).data["count"] == 1


def test_parent_cannot_use_the_staff_api_but_sees_it_on_the_portal(auth_client, make_user):
    parent = make_user(username="ieparent", role="PARENT")
    kid = make_student()
    link_guardian(kid, user=parent)
    plan = _iep(kid, status=IEP.Status.ACTIVE, primary_concern="Speech / language")
    IEPGoal.objects.create(
        iep=plan, area=IEPGoal.Area.COMMUNICATION, description="Use 4-word sentences"
    )

    c = auth_client(parent)
    assert c.get(URL).status_code == 403

    block = c.get("/api/portal/dashboard/").data["children"][0]
    assert len(block["ieps"]) == 1
    assert block["ieps"][0]["primary_concern"] == "Speech / language"
    assert block["ieps"][0]["goals"][0]["area"] == "Communication / language"


def test_parent_portal_hides_a_draft_iep(auth_client, make_user):
    parent = make_user(username="ieparent2", role="PARENT")
    kid = make_student()
    link_guardian(kid, user=parent)
    _iep(kid, status=IEP.Status.DRAFT)
    block = auth_client(parent).get("/api/portal/dashboard/").data["children"][0]
    assert block["ieps"] == []


def test_goal_viewset_is_scoped_and_iep_filtered(auth_client, staff, admin_user):
    g = make_group()
    assign_staff(g, staff)
    mine, theirs = make_student(), make_student()
    enrol(mine, g)
    p1, p2 = _iep(mine), _iep(theirs)
    IEPGoal.objects.create(iep=p1, area=IEPGoal.Area.READING, description="a")
    IEPGoal.objects.create(iep=p2, area=IEPGoal.Area.MATH, description="b")

    seen = auth_client(staff).get("/api/iep-goals/").data
    assert seen["count"] == 1

    filtered = auth_client(admin_user).get("/api/iep-goals/", {"iep": str(p1.id)}).data
    assert filtered["count"] == 1


def test_document_action_renders_the_letterhead(auth_client, admin_user):
    from apps.core.models import SchoolProfile

    SchoolProfile.load().__class__.objects.update(name="Cedar Public School")
    s = make_student(first_name="Nora", last_name="Bell")
    plan = _iep(s)
    IEPGoal.objects.create(iep=plan, area=IEPGoal.Area.WRITING, description="Write a paragraph")

    html = auth_client(admin_user).get(f"{URL}{plan.id}/document/").data["html"]
    assert "Individual Education Plan" in html
    assert "Cedar Public School" in html
    assert "Nora Bell" in html
