"""C8 -- Ministry admin/account management. apps.accounts's shared staff
directory (``UsersView``) and invite endpoint (``StaffInviteView``) are
reused as-is, made settings-driven (``ACCOUNTS_DIRECTORY_ROLES`` /
``ACCOUNTS_INVITE_MANAGER_ROLES``, central/settings/base.py) so they serve
Central's three Ministry roles instead of Campus's STAFF_ROLES -- no new
endpoints needed. Previously a known, documented gap: there was no way to
create a second Central account with a real Ministry role at all.

    pytest apps/central --ds=central.settings.test
"""
from __future__ import annotations

import pytest

from apps.accounts.models import Role, StaffInvite
from apps.central.models import DistrictAssignment

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


def test_ministry_admin_can_invite_a_district_officer(auth_client, ministry_admin):
    resp = auth_client(ministry_admin).post(
        "/api/auth/invite/",
        {"email": "new-officer@example.com", "role": "DISTRICT_OFFICER"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["role"] == "DISTRICT_OFFICER"
    invite = StaffInvite.objects.get(email="new-officer@example.com")
    assert invite.role == "DISTRICT_OFFICER"
    assert invite.invited_by == ministry_admin


def test_ministry_admin_can_invite_another_ministry_admin(auth_client, ministry_admin):
    resp = auth_client(ministry_admin).post(
        "/api/auth/invite/",
        {"email": "deputy@example.com", "role": "MINISTRY_ADMIN"},
        format="json",
    )
    assert resp.status_code == 201


def test_analyst_cannot_invite_anyone(auth_client, ministry_analyst):
    resp = auth_client(ministry_analyst).post(
        "/api/auth/invite/",
        {"email": "x@example.com", "role": "DISTRICT_OFFICER"},
        format="json",
    )
    assert resp.status_code == 403


def test_district_officer_cannot_invite_anyone(auth_client, district_officer):
    resp = auth_client(district_officer).post(
        "/api/auth/invite/",
        {"email": "x@example.com", "role": "DISTRICT_OFFICER"},
        format="json",
    )
    assert resp.status_code == 403


def test_cannot_invite_a_campus_only_role(auth_client, ministry_admin):
    """TEACHER/ADMIN/etc are Campus's own STAFF_ROLES -- meaningless on
    Central, and must be rejected by the same ChoiceField that lists
    Central's own real roles, not silently accepted."""
    resp = auth_client(ministry_admin).post(
        "/api/auth/invite/", {"email": "x@example.com", "role": "TEACHER"}, format="json"
    )
    assert resp.status_code == 400


def test_directory_lists_ministry_roles_not_campus_roles(auth_client, ministry_admin):
    resp = auth_client(ministry_admin).get("/api/auth/users/")
    assert resp.status_code == 200
    roles = {u["role"] for u in resp.data}
    assert roles <= {"SUPERADMIN", "MINISTRY_ADMIN", "MINISTRY_ANALYST", "DISTRICT_OFFICER"}


def test_district_officer_can_view_the_directory_but_not_invite(auth_client, district_officer):
    resp = auth_client(district_officer).get("/api/auth/users/")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# District assignments
# ---------------------------------------------------------------------------

def test_ministry_admin_can_assign_a_district(auth_client, ministry_admin, district_officer):
    resp = auth_client(ministry_admin).post(
        "/api/central/district-assignments/",
        {"user_id": str(district_officer.pk), "district": "Nassau"},
        format="json",
    )
    assert resp.status_code == 201
    assert DistrictAssignment.objects.filter(
        user=district_officer, district="Nassau"
    ).exists()


def test_assigning_the_same_district_twice_is_idempotent(
    auth_client, ministry_admin, district_officer
):
    client = auth_client(ministry_admin)
    body = {"user_id": str(district_officer.pk), "district": "Nassau"}
    first = client.post("/api/central/district-assignments/", body, format="json")
    second = client.post("/api/central/district-assignments/", body, format="json")
    assert first.status_code == 201
    assert second.status_code == 200
    assert DistrictAssignment.objects.filter(user=district_officer).count() == 1


def test_cannot_assign_a_district_to_a_non_district_officer(
    auth_client, ministry_admin, ministry_analyst
):
    resp = auth_client(ministry_admin).post(
        "/api/central/district-assignments/",
        {"user_id": str(ministry_analyst.pk), "district": "Nassau"},
        format="json",
    )
    assert resp.status_code == 404


def test_analyst_cannot_assign_a_district(auth_client, ministry_analyst, district_officer):
    resp = auth_client(ministry_analyst).post(
        "/api/central/district-assignments/",
        {"user_id": str(district_officer.pk), "district": "Nassau"},
        format="json",
    )
    assert resp.status_code == 403


def test_ministry_admin_can_list_and_remove_an_assignment(
    auth_client, ministry_admin, district_officer
):
    assignment = DistrictAssignment.objects.create(user=district_officer, district="Nassau")
    client = auth_client(ministry_admin)

    listed = client.get(f"/api/central/district-assignments/?user_id={district_officer.pk}")
    assert listed.status_code == 200
    assert listed.data == [{"id": str(assignment.pk), "district": "Nassau"}]

    deleted = client.delete(f"/api/central/district-assignments/{assignment.pk}/")
    assert deleted.status_code == 204
    assert not DistrictAssignment.objects.filter(pk=assignment.pk).exists()
