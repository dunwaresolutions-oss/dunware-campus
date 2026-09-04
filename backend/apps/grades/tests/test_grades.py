from __future__ import annotations

import datetime as dt

import pytest

from apps.grades.models import (
    Assessment,
    AssessmentResult,
    AssessmentScheme,
    ReportCard,
    ReportCardEntry,
)
from apps.grades.services import PdfEngineUnavailable, generate_report_card, render_report_card_html
from apps.people.tests.factories import assign_staff, enrol, link_guardian, make_group, make_student
from apps.scheduling.models import AcademicYear, Term

pytestmark = pytest.mark.django_db


def _term():
    y = AcademicYear.objects.create(name="2026-2027", start_date=dt.date(2026, 9, 1),
                                    end_date=dt.date(2027, 6, 30))
    return Term.objects.create(academic_year=y, name="T1", start_date=dt.date(2026, 9, 1),
                               end_date=dt.date(2026, 12, 20))


def test_instructor_grades_group_parent_sees_only_released(auth_client, staff, make_user):
    group = make_group()
    kid = make_student()
    enrol(kid, group)
    assign_staff(group, staff)
    parent = make_user(username="gp", role="PARENT")
    link_guardian(kid, user=parent)

    scheme = AssessmentScheme.objects.create(group=group, name="Term work",
                                             kind=AssessmentScheme.Kind.MIXED)
    assessment = Assessment.objects.create(scheme=scheme, group=group, title="Quiz 1",
                                           date=dt.date(2026, 10, 1), max_mark=10)

    teacher = auth_client(staff)
    result = teacher.post("/api/assessment-results/", {
        "assessment": str(assessment.pk), "student": str(kid.pk),
        "mark": "8.5", "narrative": "solid work",
    }, format="json")
    assert result.status_code == 201

    parent_client = auth_client(parent)
    # not released yet -> parent sees nothing
    assert parent_client.get("/api/assessment-results/").data["count"] == 0

    teacher.post(f"/api/assessments/{assessment.pk}/release/")
    assert parent_client.get("/api/assessment-results/").data["count"] == 1


def test_result_narrative_is_encrypted_at_rest():
    from django.db import connection

    group = make_group()
    kid = make_student()
    scheme = AssessmentScheme.objects.create(group=group, name="s")
    a = Assessment.objects.create(scheme=scheme, group=group, title="t", date=dt.date(2026, 9, 9))
    AssessmentResult.objects.create(assessment=a, student=kid, narrative="private feedback")
    with connection.cursor() as cur:
        cur.execute("SELECT narrative FROM grades_assessment_result")
        (raw,) = cur.fetchone()
    assert raw.startswith("cg1:") and "private" not in raw


def test_report_card_renders_html_and_degrades_without_weasyprint():
    kid = make_student(first_name="Sam", last_name="Lee")
    card = ReportCard.objects.create(student=kid, term=_term(),
                                     summary_narrative="A strong term overall.")
    ReportCardEntry.objects.create(report_card=card, subject="Numeracy", mark=88, level=3,
                                   comment="confident with addition")

    html = render_report_card_html(card)
    assert "Sam Lee" in html
    assert "Numeracy" in html
    assert "A strong term overall." in html

    result = generate_report_card(card)
    card.refresh_from_db()
    assert card.generated_at is not None
    assert card.status == ReportCard.Status.FINALIZED
    # dev/CI has no weasyprint -> html fallback, still encrypted on disk
    assert result["format"] in ("html", "pdf")
    with card.document.open("rb") as fh:
        content = fh.read()
    assert b"Numeracy" in content  # decrypts transparently
    raw_path = card.document.storage.path(card.document.name)
    with open(raw_path, "rb") as fh:
        assert fh.read().startswith(b"cf1:")
    card.document.delete(save=False)


def test_parent_only_sees_released_report_cards(auth_client, admin_user, make_user):
    kid = make_student()
    parent = make_user(username="rp", role="PARENT")
    link_guardian(kid, user=parent)
    term = _term()
    draft = ReportCard.objects.create(student=kid, term=term)

    parent_client = auth_client(parent)
    assert parent_client.get("/api/report-cards/").data["count"] == 0

    admin = auth_client(admin_user)
    admin.post(f"/api/report-cards/{draft.pk}/generate/")
    admin.post(f"/api/report-cards/{draft.pk}/release/")
    assert parent_client.get("/api/report-cards/").data["count"] == 1


def test_teacher_cannot_release_a_report_card(auth_client, staff):
    kid = make_student()
    card = ReportCard.objects.create(student=kid, term=_term())
    client = auth_client(staff)
    r = client.post(f"/api/report-cards/{card.pk}/release/")
    assert r.status_code == 403


def test_pdf_engine_helper_raises_when_absent():
    from apps.grades.services import html_to_pdf

    try:
        import weasyprint  # noqa: F401
    except Exception:
        with pytest.raises(PdfEngineUnavailable):
            html_to_pdf("<html><body>x</body></html>")
    else:  # pragma: no cover - only if a dev has weasyprint installed
        assert isinstance(html_to_pdf("<html><body>x</body></html>"), bytes)
