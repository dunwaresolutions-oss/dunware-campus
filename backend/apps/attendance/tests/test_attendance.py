from __future__ import annotations

import pytest

from apps.attendance.models import AttendanceRecord
from apps.attendance.services import NotAuthorizedToCollect, check_in, check_out
from apps.audit.models import AuditAction, AuditEntry
from apps.people.models import AuthorizedPickup, GuardianLink
from apps.people.tests.factories import (
    assign_staff,
    enrol,
    link_guardian,
    make_group,
    make_student,
)

pytestmark = pytest.mark.django_db


def test_check_in_creates_one_record_per_day():
    group = make_group()
    student = make_student()
    enrol(student, group)
    rec = check_in(student=student, group=group, dropped_off_by_name="Mum")
    assert rec.status == AttendanceRecord.Status.PRESENT
    assert rec.is_checked_in
    # idempotent for the same day
    again = check_in(student=student, group=group)
    assert again.pk == rec.pk
    assert AttendanceRecord.objects.filter(student=student).count() == 1


def test_check_out_requires_an_authorized_pickup():
    group = make_group()
    student = make_student()
    other = make_student()
    enrol(student, group)
    rec = check_in(student=student, group=group)

    stranger = AuthorizedPickup.objects.create(student=other, name="Not Yours",
                                               relationship="friend")
    with pytest.raises(NotAuthorizedToCollect):
        check_out(record_obj=rec, pickup_id=stranger.pk)

    ok = AuthorizedPickup.objects.create(
        student=student, name="Grandma", relationship="grandparent"
    )
    rec = check_out(record_obj=rec, pickup_id=ok.pk)
    assert rec.checked_out_at is not None
    assert rec.collected_by_name == "Grandma"
    assert AuditEntry.objects.filter(
        action=AuditAction.UPDATE, object_id=str(rec.pk), summary__icontains="checked out"
    ).exists()


def test_check_out_to_a_guardian_needs_can_pickup():
    group = make_group()
    student = make_student()
    enrol(student, group)
    rec = check_in(student=student, group=group)

    link = link_guardian(student, relationship=GuardianLink.Relationship.MOTHER, can_pickup=False)
    with pytest.raises(NotAuthorizedToCollect):
        check_out(record_obj=rec, guardian_link_id=link.pk)

    link.can_pickup = True
    link.save(update_fields=["can_pickup"])
    rec = check_out(record_obj=rec, guardian_link_id=link.pk)
    assert rec.collected_by_guardian_id == link.pk


def test_api_check_in_then_check_out(auth_client, front_desk):
    group = make_group()
    student = make_student()
    enrol(student, group)
    pickup = AuthorizedPickup.objects.create(student=student, name="Auntie", relationship="aunt")

    client = auth_client(front_desk)
    r1 = client.post("/api/attendance/check-in/",
                     {"student": str(student.pk), "group": str(group.pk),
                      "dropped_off_by_name": "Dad"}, format="json")
    assert r1.status_code == 200
    rec_id = r1.data["id"]

    r2 = client.post(f"/api/attendance/{rec_id}/check-out/",
                     {"pickup_id": str(pickup.pk)}, format="json")
    assert r2.status_code == 200
    assert r2.data["collected_by_name"] == "Auntie"


def test_api_check_out_unauthorized_is_403(auth_client, front_desk):
    group = make_group()
    student, other = make_student(), make_student()
    enrol(student, group)
    wrong = AuthorizedPickup.objects.create(student=other, name="Wrong", relationship="x")

    client = auth_client(front_desk)
    rec_id = client.post("/api/attendance/check-in/",
                         {"student": str(student.pk), "group": str(group.pk)},
                         format="json").data["id"]
    r = client.post(f"/api/attendance/{rec_id}/check-out/",
                    {"pickup_id": str(wrong.pk)}, format="json")
    assert r.status_code == 403


def test_teacher_only_sees_their_group_attendance(auth_client, staff):
    mine, theirs = make_group(), make_group()
    assign_staff(mine, staff)
    a, b = make_student(), make_student()
    enrol(a, mine)
    enrol(b, theirs)
    check_in(student=a, group=mine)
    check_in(student=b, group=theirs)

    client = auth_client(staff)
    resp = client.get("/api/attendance/")
    assert resp.status_code == 200
    student_ids = {str(row["student"]) for row in resp.data["results"]}
    assert student_ids == {str(a.pk)}
