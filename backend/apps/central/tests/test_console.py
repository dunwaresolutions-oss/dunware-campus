"""C6 -- the console's backend: school registry, cross-school search,
aggregate dashboards, CSV export, and the audit trail of all of it. See
docs/CENTRAL_SYNC_SCOPE.md's C0 decision 7 for why MINISTRY_ANALYST is
locked out of search specifically but not the dashboard.

    pytest apps/central --ds=central.settings.test
"""
from __future__ import annotations

import csv
import io
import uuid

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.audit.models import AuditEntry
from apps.central.models import (
    CentralAttendanceSummary,
    CentralConsent,
    CentralEnrolment,
    CentralIncidentSummary,
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


@pytest.fixture
def bootstrap_superuser(make_user):
    """The actual first account on a fresh install: role=SUPERADMIN,
    is_superuser=True -- what apps.accounts's shared SetupAdminView /
    bootstrap_superadmin() creates, reused as-is for Central's own
    first-run flow. Not a Central role at all; must still work (see
    permissions.py's own docstring on why is_superuser is a break-glass
    superset) or the very first login would be a dead end."""
    return make_user(username="root", role=Role.SUPERADMIN, is_superuser=True)


def test_bootstrap_superuser_can_use_every_console_endpoint(
    auth_client, bootstrap_superuser
):
    school = School.objects.create(name="School A", district="Nassau")
    client = auth_client(bootstrap_superuser)

    assert client.get("/api/central/schools/").status_code == 200
    assert client.get(f"/api/central/schools/{school.pk}/").status_code == 200
    assert client.get("/api/central/dashboard/").status_code == 200
    assert client.get("/api/central/search/?q=x").status_code == 200
    resp = client.post(
        "/api/central/schools/", {"name": "New School"}, format="json"
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Schools
# ---------------------------------------------------------------------------

def test_admin_sees_every_school(auth_client, ministry_admin):
    School.objects.create(name="School A", district="Nassau")
    School.objects.create(name="School B", district="Freeport")
    resp = auth_client(ministry_admin).get("/api/central/schools/")
    assert resp.status_code == 200
    assert {s["name"] for s in resp.data} == {"School A", "School B"}
    assert "sync_token_hash" not in resp.data[0]


def test_analyst_also_sees_every_school(auth_client, ministry_analyst):
    School.objects.create(name="School A", district="Nassau")
    resp = auth_client(ministry_analyst).get("/api/central/schools/")
    assert resp.status_code == 200
    assert len(resp.data) == 1


def test_district_officer_sees_only_their_own_district(auth_client, district_officer):
    DistrictAssignment.objects.create(user=district_officer, district="Nassau")
    School.objects.create(name="School A", district="Nassau")
    School.objects.create(name="School B", district="Freeport")
    resp = auth_client(district_officer).get("/api/central/schools/")
    assert resp.status_code == 200
    assert [s["name"] for s in resp.data] == ["School A"]


def test_district_officer_with_no_assignment_sees_nothing(auth_client, district_officer):
    School.objects.create(name="School A", district="Nassau")
    resp = auth_client(district_officer).get("/api/central/schools/")
    assert resp.data == []


def test_only_ministry_admin_can_register_a_school(auth_client, ministry_analyst, ministry_admin):
    resp = auth_client(ministry_analyst).post(
        "/api/central/schools/", {"name": "New School"}, format="json"
    )
    assert resp.status_code == 403

    resp = auth_client(ministry_admin).post(
        "/api/central/schools/", {"name": "New School", "district": "Nassau"}, format="json"
    )
    assert resp.status_code == 201
    assert "sync_token" in resp.data
    school = School.objects.get(name="New School")
    assert school.verify_token(resp.data["sync_token"])
    assert AuditEntry.objects.filter(action="CREATE", object_id=str(school.pk)).exists()


def test_registering_a_school_without_a_name_is_rejected(auth_client, ministry_admin):
    resp = auth_client(ministry_admin).post("/api/central/schools/", {}, format="json")
    assert resp.status_code == 400


def test_school_detail_404s_for_a_school_outside_district_officers_scope(
    auth_client, district_officer
):
    DistrictAssignment.objects.create(user=district_officer, district="Nassau")
    other = School.objects.create(name="School B", district="Freeport")
    resp = auth_client(district_officer).get(f"/api/central/schools/{other.pk}/")
    assert resp.status_code == 404


def test_school_detail_works_for_admin(auth_client, ministry_admin):
    school = School.objects.create(name="School A", district="Nassau")
    resp = auth_client(ministry_admin).get(f"/api/central/schools/{school.pk}/")
    assert resp.status_code == 200
    assert resp.data["name"] == "School A"
    assert AuditEntry.objects.filter(action="READ", object_id=str(school.pk)).exists()


def test_only_ministry_admin_can_rotate_a_token(auth_client, ministry_admin, district_officer):
    DistrictAssignment.objects.create(user=district_officer, district="Nassau")
    school = School.objects.create(name="School A", district="Nassau")
    old_hash = school.issue_token() and school.sync_token_hash

    resp = auth_client(district_officer).post(f"/api/central/schools/{school.pk}/rotate-token/")
    assert resp.status_code == 403

    resp = auth_client(ministry_admin).post(f"/api/central/schools/{school.pk}/rotate-token/")
    assert resp.status_code == 200
    school.refresh_from_db()
    assert school.sync_token_hash != old_hash
    assert school.verify_token(resp.data["sync_token"])


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def test_analyst_cannot_search_at_all(auth_client, ministry_analyst):
    resp = auth_client(ministry_analyst).get("/api/central/search/?q=kid")
    assert resp.status_code == 403


def test_admin_can_search_students_guardians_and_staff(auth_client, ministry_admin):
    school = School.objects.create(name="School A")
    CentralStudent.objects.create(
        school=school, source_id=uuid.uuid4(), first_name="Jamal", last_name="Rolle",
        date_of_birth="2018-01-01", student_number="S1", status="ENROLLED",
    )
    resp = auth_client(ministry_admin).get("/api/central/search/?q=Jamal")
    assert resp.status_code == 200
    assert resp.data["students"][0]["name"] == "Jamal Rolle"
    assert AuditEntry.objects.filter(action="READ", summary__icontains="search").exists()


def test_district_officer_search_is_scoped_to_their_district(auth_client, district_officer):
    DistrictAssignment.objects.create(user=district_officer, district="Nassau")
    in_district = School.objects.create(name="School A", district="Nassau")
    out_of_district = School.objects.create(name="School B", district="Freeport")
    CentralStudent.objects.create(
        school=in_district, source_id=uuid.uuid4(), first_name="Jamal", last_name="Rolle",
        date_of_birth="2018-01-01", student_number="S1", status="ENROLLED",
    )
    CentralStudent.objects.create(
        school=out_of_district, source_id=uuid.uuid4(), first_name="Jamal", last_name="Smith",
        date_of_birth="2018-01-01", student_number="S2", status="ENROLLED",
    )
    resp = auth_client(district_officer).get("/api/central/search/?q=Jamal")
    assert [s["student_number"] for s in resp.data["students"]] == ["S1"]


def test_search_with_no_query_returns_nothing(auth_client, ministry_admin):
    resp = auth_client(ministry_admin).get("/api/central/search/")
    assert resp.data == {"students": [], "guardians": [], "staff": []}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def _seed_dashboard_data(school):
    student_id = uuid.uuid4()
    term_id = uuid.uuid4()
    group_id = uuid.uuid4()
    CentralEnrolment.objects.create(
        school=school, source_id=uuid.uuid4(), student_source_id=student_id,
        group_source_id=group_id, start_date="2026-09-01", status="ACTIVE",
    )
    CentralAttendanceSummary.objects.create(
        school=school, student_source_id=student_id, term_source_id=term_id,
        present=8, absent=1, late=1,
    )
    CentralConsent.objects.create(
        school=school, source_id=uuid.uuid4(), student_source_id=student_id,
        kind="PHOTO", version="1", granted=True, recorded_at=timezone.now(),
    )
    CentralConsent.objects.create(
        school=school, source_id=uuid.uuid4(), student_source_id=student_id,
        kind="MEDIA", version="1", granted=False, recorded_at=timezone.now(),
    )
    CentralIncidentSummary.objects.create(
        school=school, term_source_id=term_id, category="INJURY", severity=2,
        status="SENT", count=3,
    )


def test_dashboard_aggregates_across_visible_schools(auth_client, ministry_admin):
    school = School.objects.create(name="School A")
    _seed_dashboard_data(school)
    resp = auth_client(ministry_admin).get("/api/central/dashboard/")
    assert resp.status_code == 200
    assert resp.data["enrolment_total"] == 1
    assert resp.data["attendance_pct"] == 80.0
    assert resp.data["consent_compliance_pct"] == 50.0
    assert resp.data["incidents_by_category"] == {"INJURY": 3}


def test_dashboard_illness_rate_normalizes_by_enrolment(auth_client, ministry_admin):
    """Raw illness counts aren't a fair district comparison -- a bigger
    district trivially has more incidents. Per-100-students makes it
    comparable (requested for health-concern monitoring)."""
    school = School.objects.create(name="School A")
    for _i in range(4):
        CentralEnrolment.objects.create(
            school=school, source_id=uuid.uuid4(), student_source_id=uuid.uuid4(),
            group_source_id=uuid.uuid4(), start_date="2026-09-01", status="ACTIVE",
        )
    CentralIncidentSummary.objects.create(
        school=school, term_source_id=uuid.uuid4(), category="ILLNESS", severity=1,
        status="SENT", count=2,
    )
    resp = auth_client(ministry_admin).get("/api/central/dashboard/")
    assert resp.data["enrolment_total"] == 4
    assert resp.data["illness_count"] == 2
    assert resp.data["illness_rate_per_100_students"] == 50.0


def test_dashboard_illness_rate_is_null_with_no_enrolment(auth_client, ministry_admin):
    School.objects.create(name="School A")
    resp = auth_client(ministry_admin).get("/api/central/dashboard/")
    assert resp.data["enrolment_total"] == 0
    assert resp.data["illness_count"] == 0
    assert resp.data["illness_rate_per_100_students"] is None


def test_analyst_can_view_the_dashboard_even_though_not_search(auth_client, ministry_analyst):
    school = School.objects.create(name="School A")
    _seed_dashboard_data(school)
    resp = auth_client(ministry_analyst).get("/api/central/dashboard/")
    assert resp.status_code == 200
    assert resp.data["enrolment_total"] == 1


def test_dashboard_by_district_returns_one_row_per_district(auth_client, ministry_admin):
    a = School.objects.create(name="School A", district="Nassau")
    b = School.objects.create(name="School B", district="Freeport")
    _seed_dashboard_data(a)
    _seed_dashboard_data(b)
    resp = auth_client(ministry_admin).get("/api/central/dashboard/?group_by=district")
    assert resp.status_code == 200
    districts = {row["district"] for row in resp.data["by_district"]}
    assert districts == {"Nassau", "Freeport"}


def test_dashboard_school_id_filter_narrows_to_one_school(auth_client, ministry_admin):
    a = School.objects.create(name="School A")
    b = School.objects.create(name="School B")
    _seed_dashboard_data(a)
    _seed_dashboard_data(b)
    resp = auth_client(ministry_admin).get(f"/api/central/dashboard/?school_id={a.pk}")
    assert resp.data["enrolment_total"] == 1
    assert resp.data["school_count"] == 1


def test_dashboard_with_no_data_has_null_percentages_not_a_crash(auth_client, ministry_admin):
    School.objects.create(name="Empty School")
    resp = auth_client(ministry_admin).get("/api/central/dashboard/")
    assert resp.status_code == 200
    assert resp.data["attendance_pct"] is None
    assert resp.data["consent_compliance_pct"] is None


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def test_dashboard_csv_export_has_the_right_columns_and_values(auth_client, ministry_admin):
    school = School.objects.create(name="School A")
    _seed_dashboard_data(school)
    resp = auth_client(ministry_admin).get("/api/central/dashboard/export.csv")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/csv")

    rows = list(csv.DictReader(io.StringIO(resp.content.decode("utf-8"))))
    assert len(rows) == 1
    assert rows[0]["enrolment_total"] == "1"
    assert rows[0]["attendance_pct"] == "80.0"

    assert AuditEntry.objects.filter(action="EXPORT").exists()


def test_dashboard_csv_export_by_district(auth_client, ministry_admin):
    a = School.objects.create(name="School A", district="Nassau")
    b = School.objects.create(name="School B", district="Freeport")
    _seed_dashboard_data(a)
    _seed_dashboard_data(b)
    resp = auth_client(ministry_admin).get("/api/central/dashboard/export.csv?group_by=district")
    rows = list(csv.DictReader(io.StringIO(resp.content.decode("utf-8"))))
    assert {r["district"] for r in rows} == {"Nassau", "Freeport"}
