"""C8 -- per-student/per-guardian "case file" detail views. Assembled
entirely from data already synced; never MINISTRY_ANALYST (same permission
as search).

    pytest apps/central --ds=central.settings.test
"""
from __future__ import annotations

import uuid

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.audit.models import AuditEntry
from apps.central.models import (
    CentralAttendanceSummary,
    CentralConsent,
    CentralEnrolment,
    CentralGroup,
    CentralGuardian,
    CentralReportCard,
    CentralStudent,
    DistrictAssignment,
    School,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def ministry_admin(make_user):
    return make_user(username="minister", role=Role.MINISTRY_ADMIN)


@pytest.fixture
def ministry_analyst(make_user):
    return make_user(username="analyst", role=Role.MINISTRY_ANALYST)


@pytest.fixture
def district_officer(make_user):
    return make_user(username="officer", role=Role.DISTRICT_OFFICER)


def _seed_student_with_everything(school):
    student_id = uuid.uuid4()
    group_id = uuid.uuid4()
    term_id = uuid.uuid4()
    group = CentralGroup.objects.create(
        school=school, source_id=group_id, name="Grade 7A", kind="CLASS",
    )
    student = CentralStudent.objects.create(
        school=school, source_id=student_id, first_name="Jamal", last_name="Rolle",
        date_of_birth="2018-01-01", student_number="S1", status="ACTIVE",
        primary_group_source_id=group_id, guardian_count=1,
    )
    CentralEnrolment.objects.create(
        school=school, source_id=uuid.uuid4(), student_source_id=student_id,
        group_source_id=group_id, start_date="2026-09-01", status="ACTIVE",
    )
    CentralAttendanceSummary.objects.create(
        school=school, student_source_id=student_id, term_source_id=term_id,
        present=8, absent=1, late=1, present_pct=80.0,
    )
    CentralConsent.objects.create(
        school=school, source_id=uuid.uuid4(), student_source_id=student_id,
        kind="PHOTO", version="1", granted=True, recorded_at=timezone.now(),
    )
    CentralReportCard.objects.create(
        school=school, source_id=uuid.uuid4(), student_source_id=student_id,
        term_source_id=term_id, status="RELEASED",
    )
    guardian = CentralGuardian.objects.create(
        school=school, source_id=uuid.uuid4(), first_name="Patrice", last_name="Rolle",
        email="patrice@example.com", phone="242-555-0100",
        children=[{"student_id": str(student_id), "relationship": "MOTHER"}],
    )
    return student, guardian, group


# ---------------------------------------------------------------------------
# Student detail
# ---------------------------------------------------------------------------

def test_analyst_cannot_view_student_detail(auth_client, ministry_analyst):
    school = School.objects.create(name="School A")
    student, _g, _grp = _seed_student_with_everything(school)
    resp = auth_client(ministry_analyst).get(f"/api/central/students/{student.pk}/")
    assert resp.status_code == 403


def test_admin_sees_full_student_detail(auth_client, ministry_admin):
    school = School.objects.create(name="School A", district="Nassau")
    student, guardian, group = _seed_student_with_everything(school)

    resp = auth_client(ministry_admin).get(f"/api/central/students/{student.pk}/")
    assert resp.status_code == 200
    data = resp.data
    assert data["first_name"] == "Jamal"
    assert data["school_name"] == "School A"
    assert data["school_district"] == "Nassau"
    assert data["primary_group_name"] == "Grade 7A"
    assert data["enrolments"][0]["group_name"] == "Grade 7A"
    assert data["attendance"][0]["present"] == 8
    assert data["consents"][0]["kind"] == "PHOTO"
    assert data["report_cards"][0]["status"] == "RELEASED"
    guardians = data["guardians"]
    assert guardians[0]["id"] == str(guardian.pk)
    assert guardians[0]["relationship"] == "MOTHER"
    assert guardians[0]["email"] == "patrice@example.com"
    assert AuditEntry.objects.filter(action="READ", summary__icontains="case file").exists()


def test_student_detail_404s_outside_scope(auth_client, district_officer):
    DistrictAssignment.objects.create(user=district_officer, district="Nassau")
    out_of_district = School.objects.create(name="School B", district="Freeport")
    student, _g, _grp = _seed_student_with_everything(out_of_district)
    resp = auth_client(district_officer).get(f"/api/central/students/{student.pk}/")
    assert resp.status_code == 404


def test_student_detail_404s_for_unknown_id(auth_client, ministry_admin):
    resp = auth_client(ministry_admin).get(f"/api/central/students/{uuid.uuid4()}/")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Guardian detail
# ---------------------------------------------------------------------------

def test_analyst_cannot_view_guardian_detail(auth_client, ministry_analyst):
    school = School.objects.create(name="School A")
    _s, guardian, _grp = _seed_student_with_everything(school)
    resp = auth_client(ministry_analyst).get(f"/api/central/guardians/{guardian.pk}/")
    assert resp.status_code == 403


def test_admin_sees_full_guardian_detail(auth_client, ministry_admin):
    school = School.objects.create(name="School A")
    student, guardian, _grp = _seed_student_with_everything(school)

    resp = auth_client(ministry_admin).get(f"/api/central/guardians/{guardian.pk}/")
    assert resp.status_code == 200
    data = resp.data
    assert data["first_name"] == "Patrice"
    assert data["children"][0]["student_id"] == str(student.pk)
    assert data["children"][0]["name"] == "Jamal Rolle"
    assert data["children"][0]["relationship"] == "MOTHER"
    assert AuditEntry.objects.filter(action="READ", summary__icontains="case file").exists()


def test_guardian_detail_404s_for_unknown_id(auth_client, ministry_admin):
    resp = auth_client(ministry_admin).get(f"/api/central/guardians/{uuid.uuid4()}/")
    assert resp.status_code == 404
