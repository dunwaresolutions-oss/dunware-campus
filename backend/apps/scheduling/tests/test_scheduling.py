from __future__ import annotations

import datetime as dt

import pytest
from django.core import mail

from apps.people.tests.factories import (
    assign_staff,
    enrol,
    link_guardian,
    make_group,
    make_student,
)
from apps.scheduling.models import (
    AcademicYear,
    Closure,
    EarlyDismissal,
    SessionOccurrence,
    SessionTemplate,
    Term,
)
from apps.scheduling.services import generate_occurrences

pytestmark = pytest.mark.django_db


def _term(start=dt.date(2026, 9, 1), end=dt.date(2026, 9, 30)) -> Term:
    year = AcademicYear.objects.create(name="2026-2027", start_date=start, end_date=end)
    return Term.objects.create(academic_year=year, name="Fall", start_date=start, end_date=end)


def _template(group, term, weekday=0) -> SessionTemplate:
    return SessionTemplate.objects.create(
        group=group, term=term, weekday=weekday,
        start_time=dt.time(9, 0), end_time=dt.time(10, 0), title="Circle time",
    )


def test_generate_expands_weekly_and_is_idempotent():
    term = _term()  # Sept 2026: Mondays are 7, 14, 21, 28
    tmpl = _template(make_group(), term, weekday=0)

    first = generate_occurrences(tmpl)
    assert first["created"] == 4
    assert SessionOccurrence.objects.filter(template=tmpl).count() == 4

    again = generate_occurrences(tmpl)
    assert again["created"] == 0
    assert again["skipped_existing"] == 4
    assert SessionOccurrence.objects.filter(template=tmpl).count() == 4


def test_generate_skips_closures():
    term = _term()
    group = make_group()
    tmpl = _template(group, term, weekday=0)
    # close the second Monday, site-wide
    Closure.objects.create(start_date=dt.date(2026, 9, 14), end_date=dt.date(2026, 9, 14),
                           reason="PD day")
    result = generate_occurrences(tmpl)
    assert result["created"] == 3
    assert result["skipped_closed"] == 1
    assert not SessionOccurrence.objects.filter(template=tmpl, date=dt.date(2026, 9, 14)).exists()


def test_group_specific_closure_only_blocks_that_group():
    term = _term()
    g1, g2 = make_group(), make_group()
    t1 = _template(g1, term, weekday=0)
    t2 = _template(g2, term, weekday=0)
    Closure.objects.create(start_date=dt.date(2026, 9, 7), end_date=dt.date(2026, 9, 7),
                           reason="room flooded", group=g1)
    assert generate_occurrences(t1)["created"] == 3
    assert generate_occurrences(t2)["created"] == 4


def test_roster_reads_active_enrolments_on_the_date():
    term = _term()
    group = make_group()
    tmpl = _template(group, term, weekday=0)
    generate_occurrences(tmpl)
    occ = SessionOccurrence.objects.filter(template=tmpl).first()

    a, b, c = make_student(), make_student(), make_student()
    enrol(a, group, start_date=dt.date(2026, 8, 1))
    enrol(b, group, start_date=dt.date(2026, 8, 1))
    ended = enrol(c, group, start_date=dt.date(2026, 8, 1))
    ended.end(on=dt.date(2026, 8, 20))  # left before the term

    roster_ids = {e.student_id for e in occ.roster()}
    assert roster_ids == {a.pk, b.pk}


def test_api_instructor_sees_only_their_group_sessions(auth_client, staff):
    term = _term()
    mine, theirs = make_group(), make_group()
    assign_staff(mine, staff)
    generate_occurrences(_template(mine, term, weekday=0))
    generate_occurrences(_template(theirs, term, weekday=0))

    client = auth_client(staff)
    resp = client.get("/api/sessions/")
    assert resp.status_code == 200
    group_ids = {str(row["group"]) for row in resp.data["results"]}
    assert group_ids == {str(mine.pk)}


def test_api_front_office_can_generate_via_template_action(auth_client, admin_user):
    term = _term()
    tmpl = _template(make_group(), term, weekday=2)  # Wednesdays: 2, 9, 16, 23, 30
    client = auth_client(admin_user)
    resp = client.post(f"/api/session-templates/{tmpl.pk}/generate/", {}, format="json")
    assert resp.status_code == 201
    assert resp.data["created"] == 5


CAL = "/api/sessions/calendar/"


def test_calendar_requires_a_date_range(auth_client, admin_user):
    assert auth_client(admin_user).get(CAL).status_code == 400


def test_calendar_returns_sessions_and_closures_in_range(auth_client, admin_user):
    term = _term()
    g = make_group()
    generate_occurrences(_template(g, term, weekday=0))  # Mondays in Sept 2026
    Closure.objects.create(
        start_date=dt.date(2026, 9, 15), end_date=dt.date(2026, 9, 15),
        reason="Teacher PD day",
    )
    data = auth_client(admin_user).get(
        CAL, {"from": "2026-09-01", "to": "2026-09-30"}
    ).json()
    assert {s["date"] for s in data["sessions"]} == {
        "2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28",
    }
    assert data["sessions"][0]["group_name"] == g.name
    assert len(data["closures"]) == 1 and data["closures"][0]["reason"] == "Teacher PD day"


def test_calendar_group_filter_takes_the_uuid_pk(auth_client, admin_user):
    term = _term()
    g1, g2 = make_group(), make_group()
    generate_occurrences(_template(g1, term, weekday=0))
    generate_occurrences(_template(g2, term, weekday=1))
    data = auth_client(admin_user).get(
        CAL, {"from": "2026-09-01", "to": "2026-09-30", "group": str(g1.pk)}
    ).json()
    assert data["sessions"] and {str(s["group"]) for s in data["sessions"]} == {str(g1.pk)}


def test_calendar_student_filter_shows_only_her_own_groups(auth_client, admin_user):
    """Regression test: a student's Timetable tab (fixedStudentId) must show
    only the groups she's actually enrolled in - homeroom AND every
    course-of-study section - never every group in the school. Confirms
    both that a real student= filter narrows the result, and that a
    student enrolled in two groups sees sessions from both."""
    term = _term()
    homeroom, section, unrelated = make_group(), make_group(), make_group()
    kid = make_student()
    enrol(kid, homeroom)
    enrol(kid, section)
    generate_occurrences(_template(homeroom, term, weekday=0))
    generate_occurrences(_template(section, term, weekday=1))
    generate_occurrences(_template(unrelated, term, weekday=2))

    data = auth_client(admin_user).get(
        CAL, {"from": "2026-09-01", "to": "2026-09-30", "student": str(kid.pk)}
    ).json()
    seen_groups = {str(s["group"]) for s in data["sessions"]}
    assert seen_groups == {str(homeroom.pk), str(section.pk)}
    assert str(unrelated.pk) not in seen_groups


def test_calendar_is_instructor_scoped(auth_client, staff):
    term = _term()
    mine, theirs = make_group(), make_group()
    assign_staff(mine, staff)
    generate_occurrences(_template(mine, term, weekday=0))
    generate_occurrences(_template(theirs, term, weekday=1))
    data = auth_client(staff).get(CAL, {"from": "2026-09-01", "to": "2026-09-30"}).json()
    assert {str(s["group"]) for s in data["sessions"]} == {str(mine.pk)}


def test_calendar_caps_the_span_at_62_days(auth_client, admin_user):
    data = auth_client(admin_user).get(
        CAL, {"from": "2026-01-01", "to": "2026-12-31"}
    ).json()
    assert data["to"] == "2026-03-04"  # 2026-01-01 + 62 days


# --------------------------------------------------------- early dismissals


def test_front_office_can_create_an_early_dismissal(auth_client, admin_user):
    resp = auth_client(admin_user).post(
        "/api/early-dismissals/",
        {"date": "2026-09-15", "dismissal_time": "13:00", "reason": "Storm warning"},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["group"] is None


def test_teacher_cannot_create_an_early_dismissal(auth_client, staff):
    resp = auth_client(staff).post(
        "/api/early-dismissals/",
        {"date": "2026-09-15", "dismissal_time": "13:00", "reason": "Storm warning"},
        format="json",
    )
    assert resp.status_code == 403


def test_any_staff_can_read_early_dismissals(auth_client, staff):
    EarlyDismissal.objects.create(
        date=dt.date(2026, 9, 15), dismissal_time=dt.time(13, 0), reason="Storm warning"
    )
    resp = auth_client(staff).get("/api/early-dismissals/")
    assert resp.status_code == 200
    assert resp.data["count"] == 1


def test_calendar_includes_early_dismissals_and_flags_affected_sessions(auth_client, admin_user):
    term = _term()
    g1, g2 = make_group(), make_group()
    generate_occurrences(_template(g1, term, weekday=0))  # 09:00-10:00, Mondays
    generate_occurrences(_template(g2, term, weekday=0))
    # site-wide early dismissal on the first Monday at 09:30 -- affects both
    # groups' 09:00-10:00 session (it runs past the dismissal time)
    EarlyDismissal.objects.create(
        date=dt.date(2026, 9, 7), dismissal_time=dt.time(9, 30), reason="Storm warning"
    )
    data = auth_client(admin_user).get(CAL, {"from": "2026-09-01", "to": "2026-09-30"}).json()

    assert len(data["early_dismissals"]) == 1
    assert data["early_dismissals"][0]["dismissal_time"] == "09:30"

    sept7 = [s for s in data["sessions"] if s["date"] == "2026-09-07"]
    assert len(sept7) == 2
    assert all(s["early_dismissal_time"] == "09:30" for s in sept7)
    other_days = [s for s in data["sessions"] if s["date"] != "2026-09-07"]
    assert all(s["early_dismissal_time"] is None for s in other_days)


def test_group_specific_early_dismissal_only_flags_that_groups_sessions(auth_client, admin_user):
    term = _term()
    g1, g2 = make_group(), make_group()
    generate_occurrences(_template(g1, term, weekday=0))
    generate_occurrences(_template(g2, term, weekday=0))
    EarlyDismissal.objects.create(
        date=dt.date(2026, 9, 7), dismissal_time=dt.time(9, 30), reason="Half day", group=g1,
    )
    data = auth_client(admin_user).get(CAL, {"from": "2026-09-01", "to": "2026-09-30"}).json()
    sept7 = {
        str(s["group"]): s["early_dismissal_time"]
        for s in data["sessions"] if s["date"] == "2026-09-07"
    }
    assert sept7[str(g1.pk)] == "09:30"
    assert sept7[str(g2.pk)] is None


def test_notify_early_dismissal_emails_communications_guardians(auth_client, admin_user):
    kid = make_student()
    link_guardian(kid, email="wants@example.test", receives_communications=True)
    link_guardian(kid, email="optedout@example.test", receives_communications=False)
    dismissal = EarlyDismissal.objects.create(
        date=dt.date(2026, 9, 15), dismissal_time=dt.time(13, 0), reason="Storm warning",
    )
    resp = auth_client(admin_user).post(f"/api/early-dismissals/{dismissal.pk}/notify/")
    assert resp.status_code == 200
    assert resp.data["sent"] is True
    assert len(mail.outbox) == 1
    assert "wants@example.test" in mail.outbox[0].to
    assert "optedout@example.test" not in mail.outbox[0].to
    dismissal.refresh_from_db()
    assert dismissal.notified_at is not None


def test_teacher_cannot_trigger_the_notify_action(auth_client, staff):
    dismissal = EarlyDismissal.objects.create(
        date=dt.date(2026, 9, 15), dismissal_time=dt.time(13, 0), reason="Storm warning",
    )
    resp = auth_client(staff).post(f"/api/early-dismissals/{dismissal.pk}/notify/")
    assert resp.status_code == 403
