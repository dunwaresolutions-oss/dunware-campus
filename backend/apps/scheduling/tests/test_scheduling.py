from __future__ import annotations

import datetime as dt

import pytest

from apps.people.tests.factories import assign_staff, enrol, make_group, make_student
from apps.scheduling.models import AcademicYear, Closure, SessionOccurrence, SessionTemplate, Term
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
