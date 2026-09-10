"""Role-scoped dashboard metrics — apps/reporting/metrics.py + the endpoint."""
from __future__ import annotations

import pytest

from apps.people.tests.factories import (
    assign_staff,
    enrol,
    make_group,
    make_student,
)

pytestmark = pytest.mark.django_db

URL = "/api/metrics/"


def test_parent_is_denied(auth_client, parent):
    assert auth_client(parent).get(URL).status_code == 403


def test_anonymous_is_denied(api):
    assert api.get(URL).status_code in (401, 403)


def test_instructor_scope_is_limited_to_their_groups(auth_client, staff):
    mine, theirs = make_group(), make_group()
    assign_staff(mine, staff)
    for _ in range(2):
        enrol(make_student(), mine)
    for _ in range(3):
        enrol(make_student(), theirs)

    data = auth_client(staff).get(URL).json()

    assert data["scope"]["level"] == "instructor"
    assert data["scope"]["group_count"] == 1
    assert data["scope"]["student_count"] == 2
    # instructor payload stops at wellbeing — no school-wide blocks
    assert "operations" not in data
    assert "system" not in data
    assert set(data) >= {"attendance", "enrolment", "academics", "wellbeing"}


def test_front_desk_gets_operations_but_not_system(auth_client, front_desk):
    make_student()
    data = auth_client(front_desk).get(URL).json()

    assert data["scope"]["level"] == "office"
    assert "operations" in data
    assert "billing" in data["operations"]
    assert "consent" in data["operations"]
    assert "system" not in data


def test_admin_gets_system_without_platform(auth_client, admin_user):
    data = auth_client(admin_user).get(URL).json()

    assert data["scope"]["level"] == "system"
    assert "operations" in data
    assert "security_24h" in data["system"]
    assert "staffing" in data["system"]
    assert data["system"]["backup"]["configured"] is False  # no runs recorded
    assert data["system"]["backup"]["stale"] is True
    assert "platform" not in data["system"]


def test_superadmin_gets_the_platform_block(auth_client, superadmin):
    data = auth_client(superadmin).get(URL).json()

    assert "platform" in data["system"]
    assert "legal_holds" in data["system"]["platform"]


def test_empty_database_does_not_crash(auth_client, superadmin):
    resp = auth_client(superadmin).get(URL)
    assert resp.status_code == 200
    data = resp.json()
    # no attendance rows yet -> rate is null, not a division error
    assert data["attendance"]["rate_pct"] is None
    assert data["academics"]["released_pct"] is None
    assert data["scope"]["student_count"] == 0


def test_numbers_add_up_for_the_office(auth_client, front_desk):
    g = make_group(capacity=10)
    for _ in range(4):
        enrol(make_student(), g)
    make_student(status="PROSPECTIVE")

    e = auth_client(front_desk).get(URL).json()["enrolment"]
    assert e["active"] == 4
    assert e["prospective"] == 1
    assert e["capacity_pct"] == 40.0
