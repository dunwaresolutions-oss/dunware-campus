from __future__ import annotations

import pytest

from apps.accounts.models import Role
from apps.staffchat.models import StaffChatCursor, StaffMessage

pytestmark = pytest.mark.django_db


def test_teacher_can_direct_message_another_teacher(make_user, auth_client):
    sender = make_user(username="t1", role=Role.TEACHER)
    other = make_user(username="t2", role=Role.TEACHER)
    client = auth_client(sender)

    resp = client.post(
        "/api/staff-messages/",
        {"recipient": str(other.pk), "audience": "DIRECT", "body": "running late to class"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    msg = StaffMessage.objects.get(pk=resp.data["id"])
    assert msg.sender_id == sender.pk
    assert msg.recipient_id == other.pk


def test_direct_message_needs_a_recipient(make_user, auth_client):
    sender = make_user(username="t1", role=Role.TEACHER)
    client = auth_client(sender)
    resp = client.post(
        "/api/staff-messages/", {"audience": "DIRECT", "body": "hi"}, format="json"
    )
    assert resp.status_code == 400


def test_teacher_cannot_broadcast_to_all_staff(make_user, auth_client):
    sender = make_user(username="t1", role=Role.TEACHER)
    client = auth_client(sender)
    resp = client.post(
        "/api/staff-messages/",
        {"audience": "ALL_STAFF", "body": "urgent alert"},
        format="json",
    )
    assert resp.status_code == 403


def test_front_desk_can_broadcast_to_all_teachers(make_user, auth_client):
    sender = make_user(username="fd", role=Role.FRONT_DESK)
    teacher = make_user(username="t1", role=Role.TEACHER)
    tutor = make_user(username="tu1", role=Role.TUTOR)
    client = auth_client(sender)

    resp = client.post(
        "/api/staff-messages/",
        {"audience": "TEACHERS", "body": "assembly moved to 2pm"},
        format="json",
    )
    assert resp.status_code == 201, resp.data

    teacher_inbox = auth_client(teacher).get("/api/staff-messages/").data["results"]
    assert teacher_inbox[0]["body"] == "assembly moved to 2pm"
    # a tutor doesn't see a TEACHERS broadcast
    tutor_inbox = auth_client(tutor).get("/api/staff-messages/").data["results"]
    assert all(m["body"] != "assembly moved to 2pm" for m in tutor_inbox)


def test_a_broadcast_with_a_recipient_is_rejected(make_user, auth_client):
    sender = make_user(username="fd", role=Role.FRONT_DESK)
    other = make_user(username="t1", role=Role.TEACHER)
    client = auth_client(sender)
    resp = client.post(
        "/api/staff-messages/",
        {"recipient": str(other.pk), "audience": "TEACHERS", "body": "x"},
        format="json",
    )
    assert resp.status_code == 400


def test_unread_count_and_mark_read(make_user, auth_client):
    sender = make_user(username="fd", role=Role.FRONT_DESK)
    recipient = make_user(username="t1", role=Role.TEACHER)
    sender_client = auth_client(sender)
    recipient_client = auth_client(recipient)

    sender_client.post(
        "/api/staff-messages/",
        {"recipient": str(recipient.pk), "audience": "DIRECT", "body": "please call the office"},
        format="json",
    )

    resp = recipient_client.get("/api/staff-messages/unread_count/")
    assert resp.data["unread"] == 1

    resp = recipient_client.post("/api/staff-messages/mark_read/")
    assert resp.data["unread"] == 0

    resp = recipient_client.get("/api/staff-messages/unread_count/")
    assert resp.data["unread"] == 0
    assert StaffChatCursor.objects.filter(user=recipient).exists()


def test_sending_your_own_message_does_not_bump_your_own_unread_count(make_user, auth_client):
    sender = make_user(username="fd", role=Role.FRONT_DESK)
    other = make_user(username="t1", role=Role.TEACHER)
    client = auth_client(sender)
    client.post(
        "/api/staff-messages/",
        {"recipient": str(other.pk), "audience": "DIRECT", "body": "hi"},
        format="json",
    )
    resp = client.get("/api/staff-messages/unread_count/")
    assert resp.data["unread"] == 0


def test_a_teacher_cannot_see_a_direct_message_between_two_other_teachers(make_user, auth_client):
    a = make_user(username="t1", role=Role.TEACHER)
    b = make_user(username="t2", role=Role.TEACHER)
    bystander = make_user(username="t3", role=Role.TEACHER)
    auth_client(a).post(
        "/api/staff-messages/",
        {"recipient": str(b.pk), "audience": "DIRECT", "body": "private note"},
        format="json",
    )
    inbox = auth_client(bystander).get("/api/staff-messages/").data["results"]
    assert all(m["body"] != "private note" for m in inbox)


def test_message_body_is_encrypted_at_rest(make_user, auth_client):
    from django.db import connection

    sender = make_user(username="fd", role=Role.FRONT_DESK)
    other = make_user(username="t1", role=Role.TEACHER)
    auth_client(sender).post(
        "/api/staff-messages/",
        {"recipient": str(other.pk), "audience": "DIRECT", "body": "sensitive hand-off detail"},
        format="json",
    )
    with connection.cursor() as cur:
        cur.execute("SELECT body FROM staffchat_message")
        (raw,) = cur.fetchone()
    assert raw.startswith("cg1:") and "sensitive" not in raw


def test_a_parent_gets_no_access_to_staff_chat(parent, auth_client):
    resp = auth_client(parent).get("/api/staff-messages/")
    assert resp.status_code == 403
