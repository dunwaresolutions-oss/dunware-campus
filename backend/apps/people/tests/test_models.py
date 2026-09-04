from __future__ import annotations

import pytest
from django.core.files.base import ContentFile
from django.db import connection

from apps.accounts.models import Role
from apps.audit.models import AuditAction, AuditEntry
from apps.people.models import Document, Student

from .factories import assign_staff, enrol, link_guardian, make_group, make_student

pytestmark = pytest.mark.django_db


def test_student_encrypted_fields_round_trip_and_store_ciphertext():
    s = make_student(government_id="123-456-789", custody_notes="Father has sole custody.")
    s.refresh_from_db()
    assert s.government_id == "123-456-789"
    assert s.custody_notes == "Father has sole custody."

    with connection.cursor() as cur:
        cur.execute(
            "SELECT government_id, custody_notes FROM people_student WHERE student_number = %s",
            [s.student_number],
        )
        raw_gid, raw_notes = cur.fetchone()
    assert raw_gid.startswith("cg1:")
    assert "custody" not in raw_notes.lower()


def test_creating_a_student_writes_a_create_audit_entry():
    s = make_student()
    assert AuditEntry.objects.filter(
        action=AuditAction.CREATE, object_type="people.Student", object_id=str(s.pk)
    ).exists()


def test_document_bytes_are_encrypted_on_disk():
    s = make_student()
    doc = Document.objects.create(
        student=s, kind=Document.Kind.OTHER, title="note",
        file=ContentFile(b"top secret immunization record", name="rec.txt"),
    )
    # round-trips as plaintext through the storage
    with doc.file.open("rb") as fh:
        assert fh.read() == b"top secret immunization record"
    # but the file on disk is ciphertext
    raw = doc.file.storage.path(doc.file.name)
    with open(raw, "rb") as fh:
        on_disk = fh.read()
    assert on_disk.startswith(b"cf1:")
    assert b"immunization" not in on_disk
    doc.file.delete(save=False)


def test_soft_delete_hides_from_alive():
    s = make_student()
    s.soft_delete()
    assert s.deleted_at is not None
    assert not Student.objects.alive().filter(pk=s.pk).exists()
    assert Student.objects.filter(pk=s.pk).exists()


def test_visibility_matrix(make_user):
    group_a, group_b = make_group(), make_group()
    kid_a, kid_b = make_student(), make_student()
    enrol(kid_a, group_a)
    enrol(kid_b, group_b)

    admin = make_user(username="adm", role=Role.ADMIN)
    front = make_user(username="fd", role=Role.FRONT_DESK)
    teacher_a = make_user(username="ta", role=Role.TEACHER)
    assign_staff(group_a, teacher_a)
    parent_a = make_user(username="pa", role=Role.PARENT)
    link_guardian(kid_a, user=parent_a)
    other_parent = make_user(username="po", role=Role.PARENT)

    assert kid_a.is_visible_to(admin) and kid_b.is_visible_to(admin)
    assert kid_a.is_visible_to(front) and kid_b.is_visible_to(front)
    assert kid_a.is_visible_to(teacher_a)
    assert not kid_b.is_visible_to(teacher_a)
    assert kid_a.is_visible_to(parent_a)
    assert not kid_b.is_visible_to(parent_a)
    assert not kid_a.is_visible_to(other_parent)

    assert set(Student.visible_queryset(teacher_a)) == {kid_a}
    assert set(Student.visible_queryset(parent_a)) == {kid_a}
    assert set(Student.visible_queryset(admin)) == {kid_a, kid_b}
    assert list(Student.visible_queryset(other_parent)) == []
