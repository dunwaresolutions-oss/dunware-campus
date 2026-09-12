"""GradingScheme / GradeBand — configurable report-card grading, with a
real cumulative GPA calculation when the active scheme uses one."""
from __future__ import annotations

import datetime as dt

import pytest

from apps.grades.models import GradeBand, GradingScheme, ReportCard, ReportCardEntry
from apps.grades.services import (
    compute_cumulative_gpa,
    generate_report_card,
    grade_for_mark,
)
from apps.people.tests.factories import make_student
from apps.scheduling.models import AcademicYear, Term

pytestmark = pytest.mark.django_db


def _term():
    y = AcademicYear.objects.create(
        name="2026-2027", start_date=dt.date(2026, 9, 1), end_date=dt.date(2027, 6, 30)
    )
    return Term.objects.create(
        academic_year=y, name="T1", start_date=dt.date(2026, 9, 1), end_date=dt.date(2026, 12, 20)
    )


def test_migration_seeds_four_presets_none_active():
    names = set(GradingScheme.objects.values_list("name", flat=True))
    assert names == {
        "Bahamas — 4.0 GPA",
        "Ontario — Elementary (Grades 1-8)",
        "South Africa — NCS 7-point",
        "Botswana — Letter bands",
    }
    assert not GradingScheme.objects.filter(is_active=True).exists()
    bahamas = GradingScheme.objects.get(name="Bahamas — 4.0 GPA")
    assert bahamas.uses_gpa is True
    assert bahamas.bands.count() == 10


def test_activate_deactivates_every_other_scheme():
    a = GradingScheme.objects.get(name="Bahamas — 4.0 GPA")
    b = GradingScheme.objects.get(name="Ontario — Elementary (Grades 1-8)")
    a.activate()
    assert GradingScheme.objects.get(pk=a.pk).is_active
    assert not GradingScheme.objects.get(pk=b.pk).is_active

    b.activate()
    assert GradingScheme.objects.get(pk=a.pk).is_active is False
    assert GradingScheme.objects.get(pk=b.pk).is_active is True
    assert GradingScheme.objects.filter(is_active=True).count() == 1


def test_grade_for_mark_matches_bahamas_bands():
    scheme = GradingScheme.objects.get(name="Bahamas — 4.0 GPA")
    assert grade_for_mark(95, scheme=scheme).label == "A"
    assert grade_for_mark(87, scheme=scheme).label == "A-"
    assert grade_for_mark(60, scheme=scheme).label == "C"
    assert grade_for_mark(52, scheme=scheme).label == "D"
    assert grade_for_mark(10, scheme=scheme).label == "F"
    assert grade_for_mark(None, scheme=scheme) is None


def test_grade_for_mark_with_no_active_scheme_returns_none():
    assert GradingScheme.objects.filter(is_active=True).exists() is False
    assert grade_for_mark(95) is None


def test_compute_cumulative_gpa_is_unweighted_average_of_mapped_points():
    scheme = GradingScheme.objects.get(name="Bahamas — 4.0 GPA")
    kid = make_student()
    card = ReportCard.objects.create(student=kid, term=_term())
    # A (4.00), B (3.00), F (0.00) -> mean = 2.3333... -> rounds to 2.33
    ReportCardEntry.objects.create(report_card=card, subject="Math", mark=95, order=1)
    ReportCardEntry.objects.create(report_card=card, subject="English", mark=76, order=2)
    ReportCardEntry.objects.create(report_card=card, subject="Art", mark=20, order=3)

    gpa = compute_cumulative_gpa(card.entries.all(), scheme=scheme)
    assert float(gpa) == pytest.approx(2.33)


def test_compute_cumulative_gpa_none_when_scheme_has_no_gpa():
    ontario = GradingScheme.objects.get(name="Ontario — Elementary (Grades 1-8)")
    kid = make_student()
    card = ReportCard.objects.create(student=kid, term=_term())
    ReportCardEntry.objects.create(report_card=card, subject="Math", mark=95, order=1)
    assert compute_cumulative_gpa(card.entries.all(), scheme=ontario) is None


def test_generate_report_card_freezes_scheme_and_gpa_at_generation_time():
    bahamas = GradingScheme.objects.get(name="Bahamas — 4.0 GPA")
    bahamas.activate()
    kid = make_student()
    card = ReportCard.objects.create(student=kid, term=_term())
    ReportCardEntry.objects.create(report_card=card, subject="Math", mark=95, order=1)
    ReportCardEntry.objects.create(report_card=card, subject="English", mark=76, order=2)

    generate_report_card(card)
    card.refresh_from_db()
    assert card.grading_scheme_id == bahamas.pk
    assert float(card.cumulative_gpa) == pytest.approx(3.5)  # (4.00 + 3.00) / 2

    # a later policy change must not rewrite this already-generated card
    ontario = GradingScheme.objects.get(name="Ontario — Elementary (Grades 1-8)")
    ontario.activate()
    card.refresh_from_db()
    assert card.grading_scheme_id == bahamas.pk
    assert float(card.cumulative_gpa) == pytest.approx(3.5)


def test_report_card_html_includes_grade_column_and_gpa_line():
    from apps.grades.services import render_report_card_html

    bahamas = GradingScheme.objects.get(name="Bahamas — 4.0 GPA")
    bahamas.activate()
    kid = make_student(first_name="Brianna", last_name="Adderley")
    card = ReportCard.objects.create(student=kid, term=_term())
    ReportCardEntry.objects.create(report_card=card, subject="English", mark=88, order=1)

    html = render_report_card_html(card)
    assert "A-" in html  # 88% falls in the A- band
    assert "Cumulative GPA" in html
    assert "Bahamas" in html


def test_report_card_entry_api_exposes_grade_label_and_gpa_points(auth_client, admin_user):
    bahamas = GradingScheme.objects.get(name="Bahamas — 4.0 GPA")
    bahamas.activate()
    kid = make_student()
    card = ReportCard.objects.create(student=kid, term=_term())
    ReportCardEntry.objects.create(report_card=card, subject="Math", mark=95, order=1)

    client = auth_client(admin_user)
    resp = client.get(f"/api/report-card-entries/?report_card={card.pk}")
    row = resp.data["results"][0]
    assert row["grade_label"] == "A"
    assert row["gpa_points"] == 4.0


def test_activate_action_requires_admin(auth_client, staff):
    scheme = GradingScheme.objects.get(name="Bahamas — 4.0 GPA")
    resp = auth_client(staff).post(f"/api/grading-schemes/{scheme.pk}/activate/")
    assert resp.status_code == 403


def test_activate_action_works_for_admin(auth_client, admin_user):
    scheme = GradingScheme.objects.get(name="Bahamas — 4.0 GPA")
    resp = auth_client(admin_user).post(f"/api/grading-schemes/{scheme.pk}/activate/")
    assert resp.status_code == 200
    assert resp.data["is_active"] is True
    assert GradeBand.objects.filter(scheme=scheme).exists()
