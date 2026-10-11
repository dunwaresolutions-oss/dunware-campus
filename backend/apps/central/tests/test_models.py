"""Campus Central's own data model (C3). Run with Central's own settings,
never Campus's:

    pytest apps/central --ds=central.settings.test

See docs/CENTRAL_SYNC_SCOPE.md for the field list these mirror.
"""
from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import CENTRAL_ROLES, Role, User
from apps.central.models import (
    CentralAttendanceSummary,
    CentralBillingSummary,
    CentralConsent,
    CentralEnrolment,
    CentralGroup,
    CentralGuardian,
    CentralIncidentSummary,
    CentralRegistrationCounts,
    CentralReportCard,
    CentralSettings,
    CentralStaff,
    CentralStudent,
    School,
    SnapshotBatch,
)

pytestmark = pytest.mark.django_db


def test_central_settings_is_a_singleton():
    a = CentralSettings.load()
    with pytest.raises(ValidationError):
        CentralSettings.objects.create(name="a second row")
    assert CentralSettings.objects.count() == 1
    assert CentralSettings.load().pk == a.pk


def test_school_issue_token_returns_plaintext_once_and_stores_only_a_hash():
    school = School.objects.create(name="Maple Grove Primary")
    raw = school.issue_token()
    school.refresh_from_db()
    assert school.sync_token_hash != raw
    assert len(school.sync_token_hash) == 64  # sha256 hex digest
    assert school.verify_token(raw) is True
    assert school.verify_token("something-else") is False
    assert school.verify_token("") is False


def test_school_pk_is_the_school_id_a_linked_campus_install_would_store():
    school = School.objects.create(name="A School")
    assert isinstance(school.pk, uuid.UUID)


def test_snapshot_batch_records_a_batch_against_a_school():
    school = School.objects.create(name="A School")
    batch = SnapshotBatch.objects.create(
        school=school, kind=SnapshotBatch.Kind.FULL,
        manifest={"tables": {"students": 1}}, content_hash="abc123",
    )
    assert batch.applied is False
    assert school.batches.count() == 1


def test_central_student_upserts_by_school_and_source_id_not_duplicates():
    school = School.objects.create(name="A School")
    source_id = uuid.uuid4()
    CentralStudent.objects.create(
        school=school, source_id=source_id, first_name="Kid", last_name="One",
        date_of_birth="2018-01-01", student_number="S900001", status="ENROLLED",
    )
    with pytest.raises(IntegrityError):
        CentralStudent.objects.create(
            school=school, source_id=source_id, first_name="Kid", last_name="Two",
            date_of_birth="2018-01-01", student_number="S900002", status="ENROLLED",
        )


def test_central_student_same_source_id_different_school_is_allowed():
    school_a = School.objects.create(name="School A")
    school_b = School.objects.create(name="School B")
    source_id = uuid.uuid4()
    CentralStudent.objects.create(
        school=school_a, source_id=source_id, first_name="Kid", last_name="One",
        date_of_birth="2018-01-01", student_number="S1", status="ENROLLED",
    )
    # same source_id, different school -- two different real students who
    # happen to share a UUID across two independent school databases is
    # astronomically unlikely, but the constraint is scoped per-school
    # deliberately, not globally, since source ids are only ever unique
    # within the school that minted them.
    CentralStudent.objects.create(
        school=school_b, source_id=source_id, first_name="Kid", last_name="Two",
        date_of_birth="2019-01-01", student_number="S2", status="ENROLLED",
    )
    assert CentralStudent.objects.count() == 2


def test_central_guardian_children_field_round_trips_a_list_of_dicts():
    school = School.objects.create(name="A School")
    child_id = str(uuid.uuid4())
    g = CentralGuardian.objects.create(
        school=school, source_id=uuid.uuid4(), first_name="Parent", last_name="One",
        email="p@example.test", children=[{"student_id": child_id, "relationship": "PARENT"}],
    )
    g.refresh_from_db()
    assert g.children == [{"student_id": child_id, "relationship": "PARENT"}]


def test_central_staff_table_has_no_source_updated_at_field():
    school = School.objects.create(name="A School")
    staff = CentralStaff.objects.create(
        school=school, source_id=uuid.uuid4(), username="teacher1", role="TEACHER", active=True,
    )
    assert not hasattr(staff, "source_updated_at")


def test_central_group_and_enrolment_and_consent_and_report_card_tables():
    school = School.objects.create(name="A School")
    group = CentralGroup.objects.create(
        school=school, source_id=uuid.uuid4(), name="Grade 4", kind="CLASS", live_count=20,
    )
    student_id = uuid.uuid4()
    CentralEnrolment.objects.create(
        school=school, source_id=uuid.uuid4(), student_source_id=student_id,
        group_source_id=group.source_id, start_date="2026-09-01", status="ACTIVE",
    )
    CentralConsent.objects.create(
        school=school, source_id=uuid.uuid4(), student_source_id=student_id,
        kind="PHOTO", version="1", granted=True, recorded_at=timezone.now(),
    )
    CentralReportCard.objects.create(
        school=school, source_id=uuid.uuid4(), student_source_id=student_id,
        term_source_id=uuid.uuid4(), status="FINALIZED",
    )
    assert CentralEnrolment.objects.filter(student_source_id=student_id).count() == 1
    assert CentralConsent.objects.filter(student_source_id=student_id).count() == 1
    assert CentralReportCard.objects.filter(student_source_id=student_id).count() == 1


def test_central_registration_counts_is_one_row_per_school():
    school = School.objects.create(name="A School")
    CentralRegistrationCounts.objects.create(
        school=school, applications_by_status={"SUBMITTED": 2}, waitlist_by_group={},
    )
    with pytest.raises(IntegrityError):
        CentralRegistrationCounts.objects.create(school=school, applications_by_status={"X": 1})


def test_central_attendance_summary_is_unique_per_school_student_and_term():
    school = School.objects.create(name="A School")
    term_id = uuid.uuid4()
    student_id = uuid.uuid4()
    CentralAttendanceSummary.objects.create(
        school=school, student_source_id=student_id, term_source_id=term_id,
        present=10, absent=1, late=0, present_pct=90.9,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CentralAttendanceSummary.objects.create(
            school=school, student_source_id=student_id, term_source_id=term_id, present=5,
        )


def test_central_incident_summary_is_unique_per_school_term_category_severity_status():
    school = School.objects.create(name="A School")
    term_id = uuid.uuid4()
    CentralIncidentSummary.objects.create(
        school=school, term_source_id=term_id, category="INJURY", severity=2,
        status="SENT", count=1,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CentralIncidentSummary.objects.create(
            school=school, term_source_id=term_id, category="INJURY", severity=2,
            status="SENT", count=99,
        )


def test_central_billing_summary_is_unique_per_school_and_term():
    school = School.objects.create(name="A School")
    term_id = uuid.uuid4()
    CentralBillingSummary.objects.create(
        school=school, term_source_id=term_id, issued_cents=50000, paid_cents=20000,
        outstanding_cents=30000,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CentralBillingSummary.objects.create(school=school, term_source_id=term_id, issued_cents=1)


def test_ministry_roles_are_registered_and_require_mfa():
    for role in CENTRAL_ROLES:
        user = User(username=f"user-{role}", role=role)
        user.set_password("Sup3r-Secret-Pw!")
        user.save()
        assert user.must_use_mfa is True, f"{role} should require MFA like staff do"

    assert Role.MINISTRY_ADMIN in CENTRAL_ROLES
    assert Role.MINISTRY_ANALYST in CENTRAL_ROLES
    assert Role.DISTRICT_OFFICER in CENTRAL_ROLES
