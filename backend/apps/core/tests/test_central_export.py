"""Campus Central export bundle (C2) -- apps/core/central_export.py and the
`central_export` management command. See docs/CENTRAL_SYNC_SCOPE.md for the
field list this must not exceed.
"""
from __future__ import annotations

import datetime as dt
import json
import tarfile
import uuid

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.attendance.models import AttendanceRecord
from apps.billing.models import Invoice, InvoiceLine, Payment
from apps.communication.models import IncidentReport
from apps.core.central_export import build_central_export
from apps.core.models import SiteConfiguration
from apps.grades.models import ReportCard
from apps.people.tests.factories import enrol, link_guardian, make_group, make_student
from apps.registration.models import Application, Consent, WaitlistEntry
from apps.scheduling.models import AcademicYear, Term

pytestmark = pytest.mark.django_db


def _link_and_mode():
    cfg = SiteConfiguration.load()
    cfg.deployment_mode = SiteConfiguration.DeploymentMode.SCHOOL
    cfg.school_id = uuid.uuid4()
    cfg.save()
    return cfg


def _make_term():
    year = AcademicYear.objects.create(name="2026-2027", start_date=dt.date(2026, 9, 1),
                                        end_date=dt.date(2027, 6, 30), is_current=True)
    return Term.objects.create(academic_year=year, name="Term 1",
                                start_date=dt.date(2026, 9, 1), end_date=dt.date(2026, 12, 20))


def test_students_table_is_allowlisted_and_excludes_custody_and_government_id():
    student = make_student(government_id="SECRET-ID-123", custody_notes="do not release to father")
    tables = build_central_export()
    rows = tables["students"]
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == str(student.pk)
    assert row["student_number"] == student.student_number
    assert set(row) == {
        "id", "first_name", "last_name", "date_of_birth", "student_number",
        "status", "primary_group_id", "guardian_count", "updated_at",
    }
    dumped = json.dumps(row)
    assert "SECRET-ID-123" not in dumped
    assert "do not release" not in dumped


def test_guardians_table_includes_children_and_relationship_not_custody_notes():
    student = make_student()
    link = link_guardian(student, custody_notes="restricted")
    tables = build_central_export()
    rows = tables["guardians"]
    assert len(rows) == 1
    assert rows[0]["children"] == [
        {"student_id": str(student.pk), "relationship": link.relationship}
    ]
    assert "restricted" not in json.dumps(rows[0])


def test_staff_table_lists_only_staff_roles_not_parents_or_students():
    User.objects.create_user(username="teacher1", password="x", role=Role.TEACHER)
    User.objects.create_user(username="parent1", password="x", role=Role.PARENT)
    rows = build_central_export()["staff"]
    assert len(rows) == 1
    assert rows[0]["username"] == "teacher1"
    assert rows[0]["role"] == Role.TEACHER
    assert rows[0]["active"] is True


def test_groups_table_has_live_enrolment_count():
    group = make_group(name="Grade 4", capacity=25)
    s1, s2 = make_student(), make_student()
    enrol(s1, group)
    e2 = enrol(s2, group)
    e2.end()
    rows = build_central_export()["groups"]
    row = next(r for r in rows if r["id"] == str(group.pk))
    assert row["live_count"] == 1


def test_enrolments_and_consents_tables():
    student = make_student()
    group = make_group()
    enrol(student, group)
    Consent.objects.create(student=student, kind=Consent.Kind.PHOTO, granted=True, version="2")
    tables = build_central_export()
    assert tables["enrolments"][0]["student_id"] == str(student.pk)
    assert tables["consents"][0]["kind"] == Consent.Kind.PHOTO
    assert tables["consents"][0]["granted"] is True


def test_report_cards_table_has_status_only_no_narrative():
    student = make_student()
    term = _make_term()
    ReportCard.objects.create(student=student, term=term, status=ReportCard.Status.FINALIZED,
                               summary_narrative="a secret narrative")
    rows = build_central_export()["report_cards"]
    assert rows[0]["status"] == ReportCard.Status.FINALIZED
    assert "narrative" not in json.dumps(rows[0])


def test_registration_counts_are_aggregate_not_raw_applications():
    group = make_group()
    Application.objects.create(
        child_first_name="A", child_last_name="B", child_date_of_birth=dt.date(2019, 1, 1),
        applicant_name="Parent", applicant_email="p@example.test",
        status=Application.Status.SUBMITTED,
    )
    app2 = Application.objects.create(
        child_first_name="C", child_last_name="D", child_date_of_birth=dt.date(2019, 1, 1),
        applicant_name="Parent2", applicant_email="p2@example.test",
        status=Application.Status.WAITLISTED,
    )
    WaitlistEntry.objects.create(application=app2, group=group, active=True)
    rows = build_central_export()["registration_counts"]
    assert len(rows) == 1
    assert rows[0]["applications_by_status"]["SUBMITTED"] == 1
    assert rows[0]["applications_by_status"]["WAITLISTED"] == 1
    assert rows[0]["waitlist_by_group"][str(group.pk)] == 1
    # no child name or applicant email anywhere in this table
    assert "Parent" not in json.dumps(rows)


def test_attendance_summary_is_per_student_per_term_counts_only():
    student = make_student()
    group = make_group()
    term = _make_term()
    for day, status in [(1, "PRESENT"), (2, "PRESENT"), (3, "ABSENT"), (4, "LATE")]:
        AttendanceRecord.objects.create(
            student=student, group=group, date=dt.date(2026, 9, day), status=status,
        )
    rows = build_central_export()["attendance_summary"]
    row = next(
        r for r in rows if r["student_id"] == str(student.pk) and r["term_id"] == str(term.pk)
    )
    assert row["present"] == 2 and row["absent"] == 1 and row["late"] == 1
    assert row["present_pct"] == 50.0


def test_incident_summary_is_counts_only_no_description():
    student = make_student()
    term = _make_term()
    IncidentReport.objects.create(
        student=student, occurred_at=timezone.make_aware(dt.datetime(2026, 9, 15)),
        category=IncidentReport.Category.INJURY, severity=2,
        description="fell off the slide, bruised knee", status=IncidentReport.Status.SENT,
    )
    rows = build_central_export()["incident_summary"]
    row = next(r for r in rows if r["term_id"] == str(term.pk))
    assert row["category"] == IncidentReport.Category.INJURY
    assert row["count"] == 1
    assert "bruised" not in json.dumps(rows)


def test_billing_summary_is_term_totals_not_per_family(settings):
    student = make_student()
    term = _make_term()
    inv = Invoice.objects.create(student=student, term=term, status=Invoice.Status.ISSUED)
    InvoiceLine.objects.create(
        invoice=inv, description="Tuition", quantity=1, unit_amount_cents=50000
    )
    Payment.objects.create(invoice=inv, amount_cents=20000, received_at=timezone.now())
    rows = build_central_export()["billing_summary"]
    row = next(r for r in rows if r["term_id"] == str(term.pk))
    assert row["issued_cents"] == 50000
    assert row["paid_cents"] == 20000
    assert row["outstanding_cents"] == 30000
    assert "student" not in json.dumps(rows) and "guardian" not in json.dumps(rows)


def test_billing_summary_is_empty_when_the_school_does_not_collect_fees():
    student = make_student()
    term = _make_term()
    inv = Invoice.objects.create(student=student, term=term, status=Invoice.Status.ISSUED)
    InvoiceLine.objects.create(
        invoice=inv, description="Tuition", quantity=1, unit_amount_cents=50000
    )
    SiteConfiguration.objects.update(collects_fees=False)
    assert build_central_export()["billing_summary"] == []


def test_since_filters_row_level_tables_to_recently_updated_rows():
    old = make_student()
    Student = old.__class__
    Student.objects.filter(pk=old.pk).update(updated_at=timezone.now() - dt.timedelta(days=30))
    cutoff = timezone.now() - dt.timedelta(days=1)
    new = make_student()
    rows = build_central_export(since=cutoff)["students"]
    ids = {r["id"] for r in rows}
    assert str(new.pk) in ids
    assert str(old.pk) not in ids


def test_central_export_command_refuses_without_a_school_id():
    with pytest.raises(Exception):  # noqa: B017 - CommandError
        call_command("central_export", "--out", "ignored.tar.gz")


def test_central_export_command_writes_a_readable_bundle(tmp_path):
    _link_and_mode()
    make_student()
    out = tmp_path / "bundle.tar.gz"
    call_command("central_export", "--out", str(out))

    assert out.exists()
    with tarfile.open(out, mode="r:gz") as tar:
        names = tar.getnames()
        assert "manifest.json" in names
        assert "students.jsonl" in names
        manifest = json.loads(tar.extractfile("manifest.json").read())
        assert manifest["kind"] == "FULL"
        assert manifest["tables"]["students"] == 1
        assert "content_hash" in manifest
        students_jsonl = tar.extractfile("students.jsonl").read().decode("utf-8").strip()
        assert len(students_jsonl.splitlines()) == 1


def test_central_export_command_rejects_a_bad_since_value():
    _link_and_mode()
    with pytest.raises(Exception):  # noqa: B017 - CommandError
        call_command("central_export", "--out", "ignored.tar.gz", "--since", "not-a-date")


def test_central_export_command_incremental_flag_marks_the_manifest(tmp_path):
    _link_and_mode()
    make_student()
    out = tmp_path / "bundle.tar.gz"
    call_command("central_export", "--out", str(out), "--since", "2020-01-01T00:00:00")
    with tarfile.open(out, mode="r:gz") as tar:
        manifest = json.loads(tar.extractfile("manifest.json").read())
    assert manifest["kind"] == "INCREMENTAL"
    assert manifest["since"] is not None
