from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.people.tests.factories import link_guardian, make_student
from apps.registration.models import Application, Consent

pytestmark = pytest.mark.django_db


def _payload(**kw):
    base = {
        "child_first_name": "Ap", "child_last_name": "Plicant",
        "child_date_of_birth": "2021-01-01",
        "applicant_name": "Guard Ian", "applicant_email": "g@example.test",
    }
    base.update(kw)
    return base


def test_front_desk_can_create_an_application(auth_client, front_desk):
    client = auth_client(front_desk)
    resp = client.post("/api/applications/", _payload(), format="json")
    assert resp.status_code == 201
    assert resp.data["status"] == Application.Status.SUBMITTED


def test_teacher_cannot_touch_applications(auth_client, staff):
    client = auth_client(staff)
    assert client.get("/api/applications/").status_code == 403
    assert client.post("/api/applications/", _payload(), format="json").status_code == 403


def test_review_and_decline_actions(auth_client, admin_user):
    client = auth_client(admin_user)
    app_id = client.post("/api/applications/", _payload(), format="json").data["id"]
    assert client.post(f"/api/applications/{app_id}/review/").data["status"] == "UNDER_REVIEW"
    assert client.post(f"/api/applications/{app_id}/decline/").data["status"] == "DECLINED"


def test_parent_sees_only_their_childs_consents(auth_client, make_user):
    kid_a, kid_b = make_student(), make_student()
    parent = make_user(username="pp", role="PARENT")
    link_guardian(kid_a, user=parent)
    Consent.objects.create(student=kid_a, kind=Consent.Kind.PHOTO, granted=True)
    Consent.objects.create(student=kid_b, kind=Consent.Kind.PHOTO, granted=True)

    client = auth_client(parent)
    resp = client.get("/api/consents/")
    assert resp.status_code == 200
    student_ids = {str(row["student"]) for row in resp.data["results"]}
    assert student_ids == {str(kid_a.pk)}


def test_offer_and_convert_over_the_api(auth_client, admin_user):
    from apps.people.tests.factories import make_group

    group = make_group()
    client = auth_client(admin_user)
    app_id = client.post("/api/applications/", _payload(), format="json").data["id"]
    offer = client.post(f"/api/applications/{app_id}/make_offer/", {
        "group": str(group.pk),
        "start_date": "2026-09-15",
        "expires_at": (timezone.now() + dt.timedelta(days=14)).isoformat(),
    }, format="json")
    assert offer.status_code == 201
    conv = client.post(f"/api/applications/{app_id}/convert/", {"group": str(group.pk)},
                       format="json")
    assert conv.status_code == 201
    assert conv.data["student"] and conv.data["enrolment"]
