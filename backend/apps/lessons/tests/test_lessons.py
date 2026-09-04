from __future__ import annotations

import datetime as dt

import pytest

from apps.lessons.models import CurriculumUnit, LessonPlan
from apps.people.tests.factories import assign_staff, make_group

pytestmark = pytest.mark.django_db


def test_instructor_can_create_and_publish_a_plan_for_their_group(auth_client, staff):
    group = make_group()
    assign_staff(group, staff)
    client = auth_client(staff)

    unit = client.post("/api/curriculum-units/",
                       {"group": str(group.pk), "title": "Numbers 1-10", "sequence": 1},
                       format="json")
    assert unit.status_code == 201

    plan = client.post("/api/lesson-plans/", {
        "group": str(group.pk), "unit": unit.data["id"], "date": "2026-09-10",
        "title": "Counting bears", "objectives": "count to 10",
    }, format="json")
    assert plan.status_code == 201
    assert plan.data["status"] == "DRAFT"
    assert plan.data["author"] is not None

    pub = client.post(f"/api/lesson-plans/{plan.data['id']}/publish/")
    assert pub.data["status"] == "PUBLISHED"


def test_instructor_cannot_see_another_groups_plans(auth_client, staff):
    mine, theirs = make_group(), make_group()
    assign_staff(mine, staff)
    CurriculumUnit.objects.create(group=theirs, title="not yours")
    LessonPlan.objects.create(group=theirs, date=dt.date(2026, 9, 1), title="secret")

    client = auth_client(staff)
    assert client.get("/api/lesson-plans/").data["count"] == 0
    assert client.get("/api/curriculum-units/").data["count"] == 0


def test_admin_sees_everything(auth_client, admin_user):
    g1, g2 = make_group(), make_group()
    LessonPlan.objects.create(group=g1, date=dt.date(2026, 9, 1), title="a")
    LessonPlan.objects.create(group=g2, date=dt.date(2026, 9, 2), title="b")
    client = auth_client(admin_user)
    assert client.get("/api/lesson-plans/").data["count"] == 2
