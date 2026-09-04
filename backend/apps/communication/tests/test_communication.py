from __future__ import annotations

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.audit.models import AuditAction, AuditEntry
from apps.communication.models import Announcement, IncidentReport, OutboundEmail
from apps.communication.services import notify_incident, send_announcement
from apps.people.tests.factories import (
    assign_staff,
    enrol,
    link_guardian,
    make_group,
    make_student,
)

pytestmark = pytest.mark.django_db


def test_announcement_email_goes_to_comms_guardians_only(make_user):
    group = make_group()
    kid = make_student()
    enrol(kid, group)
    link_guardian(kid, email="wants@example.test", receives_communications=True)
    link_guardian(kid, email="optedout@example.test", receives_communications=False)

    ann = Announcement.objects.create(
        title="Snow day", body="Closed tomorrow.",
        audience=Announcement.Audience.GROUP, group=group,
        published_at=timezone.now(),
    )
    log = send_announcement(ann)
    assert log.sent_at is not None
    assert "wants@example.test" in log.to
    assert "optedout@example.test" not in log.to
    assert len(mail.outbox) == 1
    ann.refresh_from_db()
    assert ann.email_sent_at is not None


def test_incident_notify_flips_status_and_logs(make_user):
    kid = make_student()
    link_guardian(kid, email="parent@example.test")
    incident = IncidentReport.objects.create(
        student=kid, occurred_at=timezone.now() - timedelta(hours=1),
        category=IncidentReport.Category.INJURY, description="grazed knee",
    )
    notify_incident(incident)
    incident.refresh_from_db()
    assert incident.status == IncidentReport.Status.SENT
    assert incident.guardians_notified_at is not None
    assert OutboundEmail.objects.filter(kind=OutboundEmail.Kind.INCIDENT).exists()


def test_incident_description_is_encrypted_at_rest():
    from django.db import connection

    kid = make_student()
    IncidentReport.objects.create(
        student=kid, occurred_at=timezone.now(),
        category=IncidentReport.Category.OTHER, description="sensitive detail here",
    )
    with connection.cursor() as cur:
        cur.execute("SELECT description FROM communication_incident_report")
        (raw,) = cur.fetchone()
    assert raw.startswith("cg1:") and "sensitive" not in raw


def test_parent_only_sees_sent_incidents_for_their_child(auth_client, make_user):
    kid_a, kid_b = make_student(), make_student()
    parent = make_user(username="pc", role="PARENT")
    link_guardian(kid_a, user=parent)

    draft = IncidentReport.objects.create(
        student=kid_a, occurred_at=timezone.now(),
        category=IncidentReport.Category.OTHER, description="draft note",
    )
    sent = IncidentReport.objects.create(
        student=kid_a, occurred_at=timezone.now(),
        category=IncidentReport.Category.OTHER, description="sent note",
        status=IncidentReport.Status.SENT,
    )
    IncidentReport.objects.create(
        student=kid_b, occurred_at=timezone.now(),
        category=IncidentReport.Category.OTHER, description="other kid",
        status=IncidentReport.Status.SENT,
    )

    client = auth_client(parent)
    resp = client.get("/api/incident-reports/")
    assert resp.status_code == 200
    ids = {str(r["id"]) for r in resp.data["results"]}
    assert ids == {str(sent.pk)}
    assert str(draft.pk) not in ids


def test_full_acknowledgement_flow(auth_client, staff, make_user):
    group = make_group()
    kid = make_student()
    enrol(kid, group)
    assign_staff(group, staff)
    parent = make_user(username="ack", role="PARENT")
    link_guardian(kid, user=parent, email="ack@example.test", receives_communications=True)

    # teacher files + notifies
    teacher_client = auth_client(staff)
    filed = teacher_client.post("/api/incident-reports/", {
        "student": str(kid.pk),
        "occurred_at": timezone.now().isoformat(),
        "category": "BEHAVIOUR",
        "description": "pushed another child",
    }, format="json")
    assert filed.status_code == 201
    incident_id = filed.data["id"]
    notified = teacher_client.post(f"/api/incident-reports/{incident_id}/notify/")
    assert notified.status_code == 200
    assert notified.data["status"] == "SENT"

    # parent acknowledges
    parent_client = auth_client(parent)
    ack = parent_client.post("/api/incident-acknowledgements/", {
        "incident": incident_id, "signature_name": "A Parent",
    }, format="json")
    assert ack.status_code == 201

    incident = IncidentReport.objects.get(pk=incident_id)
    assert incident.status == IncidentReport.Status.ACKNOWLEDGED
    assert AuditEntry.objects.filter(action=AuditAction.CREATE,
                                     object_type="communication.IncidentReport").exists()


def test_message_thread_is_participant_scoped(auth_client, staff, make_user):
    parent = make_user(username="mp", role="PARENT")
    outsider = make_user(username="mo", role="PARENT")

    staff_client = auth_client(staff)
    thread = staff_client.post("/api/message-threads/", {
        "subject": "About drop-off", "participants": [str(parent.pk)],
    }, format="json")
    assert thread.status_code == 201
    tid = thread.data["id"]

    msg = staff_client.post("/api/messages/", {"thread": tid, "body": "Hello"}, format="json")
    assert msg.status_code == 201

    assert auth_client(parent).get(f"/api/message-threads/{tid}/").status_code == 200
    assert auth_client(outsider).get(f"/api/message-threads/{tid}/").status_code == 404
