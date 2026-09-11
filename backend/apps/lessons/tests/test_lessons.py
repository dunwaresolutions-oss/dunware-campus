from __future__ import annotations

import datetime as dt

import pytest

from apps.lessons.models import CurriculumUnit, LessonPlan, LessonResource
from apps.people.tests.factories import assign_staff, make_group
from apps.scheduling.models import Term

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


def _term():
    from apps.scheduling.models import AcademicYear

    start, end = dt.date(2026, 9, 1), dt.date(2026, 12, 20)
    year = AcademicYear.objects.create(name="2026-2027", start_date=start, end_date=end)
    return Term.objects.create(academic_year=year, name="Fall", start_date=start, end_date=end)


def test_lesson_plans_filter_by_group_unit_status_and_term(auth_client, admin_user):
    g1, g2 = make_group(), make_group()
    term = _term()
    unit = CurriculumUnit.objects.create(group=g1, title="Numbers", term=term)
    draft = LessonPlan.objects.create(group=g1, unit=unit, date=dt.date(2026, 9, 1), title="a")
    LessonPlan.objects.create(
        group=g1, date=dt.date(2026, 9, 2), title="b", status=LessonPlan.Status.PUBLISHED
    )
    LessonPlan.objects.create(group=g2, date=dt.date(2026, 9, 3), title="c")

    client = auth_client(admin_user)
    assert client.get(f"/api/lesson-plans/?group={g1.pk}").data["count"] == 2
    assert client.get(f"/api/lesson-plans/?unit={unit.pk}").data["count"] == 1
    assert client.get("/api/lesson-plans/?status=PUBLISHED").data["count"] == 1
    resp = client.get(f"/api/lesson-plans/?term={term.pk}")
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["id"] == str(draft.pk)


def test_curriculum_units_filter_by_group_and_term(auth_client, admin_user):
    g1, g2 = make_group(), make_group()
    term = _term()
    unit_a = CurriculumUnit.objects.create(group=g1, title="A", term=term)
    CurriculumUnit.objects.create(group=g2, title="B")

    client = auth_client(admin_user)
    resp = client.get(f"/api/curriculum-units/?group={g1.pk}")
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["id"] == str(unit_a.pk)
    assert client.get(f"/api/curriculum-units/?term={term.pk}").data["count"] == 1


def test_lesson_resource_inherits_group_from_its_lesson(auth_client, admin_user):
    group = make_group()
    plan = LessonPlan.objects.create(group=group, date=dt.date(2026, 9, 1), title="a")
    client = auth_client(admin_user)
    resp = client.post(
        "/api/lesson-resources/",
        {"lesson": str(plan.pk), "kind": "NOTE", "title": "Reading list", "body": "x"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    resource = LessonResource.objects.get(pk=resp.data["id"])
    assert resource.group_id == group.pk
    assert resp.data["group_name"] == group.name


def test_lesson_resource_can_be_attached_to_a_group_directly(auth_client, admin_user):
    group = make_group()
    client = auth_client(admin_user)
    resp = client.post(
        "/api/lesson-resources/",
        {"group": str(group.pk), "kind": "LINK", "title": "Class portal", "url": "https://x.test"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["lesson"] is None


def test_lesson_resource_needs_a_group_or_a_lesson(auth_client, admin_user):
    client = auth_client(admin_user)
    resp = client.post(
        "/api/lesson-resources/", {"kind": "NOTE", "title": "orphan", "body": "x"}, format="json"
    )
    assert resp.status_code == 400


def test_lesson_resources_filter_by_group(auth_client, admin_user):
    g1, g2 = make_group(), make_group()
    LessonResource.objects.create(group=g1, kind=LessonResource.Kind.NOTE, title="a", body="x")
    LessonResource.objects.create(group=g2, kind=LessonResource.Kind.NOTE, title="b", body="x")

    client = auth_client(admin_user)
    resp = client.get(f"/api/lesson-resources/?group={g1.pk}")
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["title"] == "a"


def test_instructor_can_only_see_resources_for_their_own_group(auth_client, staff):
    mine, theirs = make_group(), make_group()
    assign_staff(mine, staff)
    LessonResource.objects.create(
        group=mine, kind=LessonResource.Kind.NOTE, title="mine", body="x"
    )
    LessonResource.objects.create(
        group=theirs, kind=LessonResource.Kind.NOTE, title="theirs", body="x"
    )

    client = auth_client(staff)
    resp = client.get("/api/lesson-resources/")
    titles = {row["title"] for row in resp.data["results"]}
    assert titles == {"mine"}
