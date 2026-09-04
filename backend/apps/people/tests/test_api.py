from __future__ import annotations

import pytest

from apps.audit.models import AuditAction, AuditEntry

from .factories import assign_staff, enrol, link_guardian, make_group, make_student

pytestmark = pytest.mark.django_db


def test_anonymous_is_denied(api):
    assert api.get("/api/students/").status_code in (401, 403)


def test_unverified_staff_is_denied(api, staff):
    # log in without the OTP step: session exists but not MFA-verified
    api.post("/api/auth/login/", {"username": "teacher", "password": "Sup3r-Secret-Pw!"},
             format="json")
    assert api.get("/api/students/").status_code == 403


def test_front_desk_can_create_and_list_students(auth_client, front_desk):
    client = auth_client(front_desk)
    resp = client.post("/api/students/", {
        "first_name": "New", "last_name": "Kid", "date_of_birth": "2019-05-05",
    }, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["student_number"]  # auto-allocated
    assert client.get("/api/students/").status_code == 200
    assert AuditEntry.objects.filter(action=AuditAction.READ, summary__startswith="listed").exists()


def test_parent_sees_only_their_child(auth_client, make_user):
    kid_a, kid_b = make_student(), make_student()
    parent = make_user(username="mum", role="PARENT")
    link_guardian(kid_a, user=parent)

    client = auth_client(parent)
    listing = client.get("/api/students/")
    assert listing.status_code == 200
    ids = {str(row["id"]) for row in listing.data["results"]}
    assert ids == {str(kid_a.pk)}
    assert client.get(f"/api/students/{kid_a.pk}/").status_code == 200
    assert client.get(f"/api/students/{kid_b.pk}/").status_code == 404


def test_teacher_scoped_to_their_group(auth_client, staff):
    group = make_group()
    mine, theirs = make_student(), make_student()
    enrol(mine, group)
    assign_staff(group, staff)

    client = auth_client(staff)
    assert client.get(f"/api/students/{mine.pk}/").status_code == 200
    assert client.get(f"/api/students/{theirs.pk}/").status_code == 404


def test_retrieve_writes_a_read_audit_entry(auth_client, front_desk):
    kid = make_student()
    client = auth_client(front_desk)
    client.get(f"/api/students/{kid.pk}/")
    assert AuditEntry.objects.filter(
        action=AuditAction.READ, object_type="people.Student", object_id=str(kid.pk)
    ).exists()
