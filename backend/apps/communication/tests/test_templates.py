"""Message templates — the token registry, rendering, the API, and the wired
notification paths."""
from __future__ import annotations

import datetime as dt

import pytest
from django.core import mail
from django.utils import timezone

from apps.communication.models import IncidentReport, MessageTemplate
from apps.communication.services import notify_incident
from apps.communication.templating import build_context, get_active, render_template
from apps.communication.tokens import available_tokens, render
from apps.core.models import SchoolProfile
from apps.people.tests.factories import link_guardian, make_student

pytestmark = pytest.mark.django_db

URL = "/api/message-templates/"


def test_migration_seeded_the_system_templates():
    keys = set(MessageTemplate.objects.values_list("key", flat=True))
    assert {
        "incident_notification", "report_card_released",
        "absence_notification", "announcement_email",
    } <= keys
    assert get_active(MessageTemplate.Kind.INCIDENT).key == "incident_notification"


def test_token_palette_is_kind_aware():
    inc = {g["group"] for g in available_tokens("INCIDENT")}
    ann = {g["group"] for g in available_tokens("ANNOUNCEMENT")}
    assert {"Student", "Guardian", "Incident"} <= inc
    assert "Guardian" not in ann and "Announcement" in ann


def test_render_substitutes_known_blanks_missing_leaves_unknown():
    ctx = build_context(school=SchoolProfile(name="Oak School"))
    out = render("[[SCHOOL_NAME]] / [[STUDENT_FULL_NAME]] / [[NOT_A_TOKEN]]", ctx)
    assert out == "Oak School /  / [[NOT_A_TOKEN]]"


def test_render_template_resolves_real_student_and_guardian():
    s = make_student(first_name="Robert", preferred_name="Bobby", last_name="Adams")
    link = link_guardian(s, first_name="Alex", last_name="Adams")
    SchoolProfile.load()  # ensure a row
    tmpl = get_active(MessageTemplate.Kind.INCIDENT)
    subject, body = render_template(
        tmpl, build_context(student=s, guardian=link.guardian, event=timezone.now())
    )
    assert "Bobby" in subject
    assert "Dear Alex Adams," in body
    assert "Bobby Adams" in body


def test_api_read_is_staff_write_is_front_office(auth_client, staff, front_desk):
    assert auth_client(staff).get(URL).status_code == 200
    payload = {"key": "welcome", "name": "Welcome", "kind": "GENERAL",
               "subject": "Hi [[STUDENT_FIRST_NAME]]", "body": "Welcome!"}
    assert auth_client(staff).post(URL, payload, format="json").status_code == 403
    assert auth_client(front_desk).post(URL, payload, format="json").status_code == 201


def test_api_refuses_to_delete_a_system_template(auth_client, admin_user):
    sys_t = MessageTemplate.objects.get(key="incident_notification")
    resp = auth_client(admin_user).delete(f"{URL}{sys_t.pk}/")
    assert resp.status_code == 400
    assert MessageTemplate.objects.filter(pk=sys_t.pk).exists()


def test_api_tokens_and_preview_actions(auth_client, admin_user):
    make_student(first_name="Sam", last_name="Lee")
    sys_t = MessageTemplate.objects.get(key="incident_notification")
    c = auth_client(admin_user)

    toks = c.get(f"{URL}tokens/", {"kind": "INCIDENT"}).json()
    assert any(g["group"] == "Guardian" for g in toks)

    prev = c.post(
        f"{URL}{sys_t.pk}/preview/",
        {"subject": "For [[STUDENT_FULL_NAME]]", "body": "Dear [[GUARDIAN_FULL_NAME]]"},
        format="json",
    ).json()
    assert prev["subject"].startswith("For ")
    assert prev["body"].startswith("Dear ")


def test_notify_incident_sends_one_personalised_email_per_guardian(admin_user):
    s = make_student(first_name="Mia", last_name="Nolan")
    link_guardian(s, first_name="Pat", last_name="Nolan", email="pat@example.test")
    link_guardian(s, first_name="Jo", last_name="Nolan", email="jo@example.test")
    SchoolProfile.load()
    inc = IncidentReport.objects.create(
        student=s, occurred_at=timezone.now() - dt.timedelta(hours=1),
        category=IncidentReport.Category.INJURY, description="scraped knee",
    )
    mail.outbox.clear()
    log = notify_incident(inc, actor=admin_user)

    assert len(mail.outbox) == 2
    greetings = sorted(m.body.splitlines()[0] for m in mail.outbox)
    assert greetings == ["Dear Jo Nolan,", "Dear Pat Nolan,"]
    assert set(log.to) == {"pat@example.test", "jo@example.test"}
    inc.refresh_from_db()
    assert inc.status == IncidentReport.Status.SENT
