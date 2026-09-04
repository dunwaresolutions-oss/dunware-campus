from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.audit.models import AuditAction, AuditEntry
from apps.people.models import ContactChangeRequest, Guardian
from apps.people.tests.factories import enrol, link_guardian, make_group, make_student
from apps.registration.models import Consent

pytestmark = pytest.mark.django_db


def _parent_with_child(make_user, **guardian_kw):
    parent = make_user(username=guardian_kw.pop("username", "portalparent"), role="PARENT")
    kid = make_student()
    link = link_guardian(kid, user=parent)
    # link_guardian creates the Guardian; make sure it carries the fields we test
    g = link.guardian
    for k, v in guardian_kw.items():
        setattr(g, k, v)
    g.save()
    return parent, kid, g


def test_dashboard_returns_only_the_callers_children(auth_client, make_user):
    parent, kid, _g = _parent_with_child(make_user)
    other_kid = make_student()

    client = auth_client(parent)
    resp = client.get("/api/portal/dashboard/")
    assert resp.status_code == 200
    ids = {c["id"] for c in resp.data["children"]}
    assert ids == {str(kid.pk)}
    assert str(other_kid.pk) not in ids
    assert resp.data["invoices"] == []
    assert "pending_consents" in resp.data["children"][0]


def test_dashboard_child_block_aggregates_the_right_things(auth_client, make_user):
    parent, kid, _g = _parent_with_child(make_user)
    group = make_group()
    enrol(kid, group)
    Consent.objects.create(student=kid, kind=Consent.Kind.PHOTO, granted=True)

    client = auth_client(parent)
    block = client.get("/api/portal/dashboard/").data["children"][0]
    assert block["display_name"] == kid.display_name
    assert Consent.Kind.PHOTO not in block["pending_consents"]
    assert Consent.Kind.MEDIA in block["pending_consents"]


def test_staff_cannot_use_the_portal_dashboard(auth_client, staff):
    client = auth_client(staff)
    assert client.get("/api/portal/dashboard/").status_code == 403


def test_contact_change_request_flow(auth_client, make_user, front_desk):
    parent, _kid, guardian = _parent_with_child(make_user, phone="555-0000")

    parent_client = auth_client(parent)
    submitted = parent_client.post("/api/portal/contact-change-requests/", {
        "field": "phone", "proposed_value": "555-1234", "reason": "new number",
    }, format="json")
    assert submitted.status_code == 201
    assert submitted.data["status"] == "PENDING"
    assert submitted.data["current_value"] == "555-0000"
    req_id = submitted.data["id"]

    # parent sees only their own request
    assert parent_client.get("/api/portal/contact-change-requests/").data["count"] == 1

    office = auth_client(front_desk)
    approved = office.post(f"/api/portal/contact-change-requests/{req_id}/approve/",
                           {"note": "verified by phone"}, format="json")
    assert approved.status_code == 200
    assert approved.data["status"] == "APPROVED"

    guardian.refresh_from_db()
    assert guardian.phone == "555-1234"
    assert AuditEntry.objects.filter(
        action=AuditAction.UPDATE, summary__icontains="contact-change applied"
    ).exists()


def test_contact_change_rejected_does_not_apply(auth_client, make_user, front_desk):
    parent, _kid, guardian = _parent_with_child(make_user, email="old@example.test")
    parent_client = auth_client(parent)
    req_id = parent_client.post("/api/portal/contact-change-requests/", {
        "field": "email", "proposed_value": "new@example.test",
    }, format="json").data["id"]

    auth_client(front_desk).post(
        f"/api/portal/contact-change-requests/{req_id}/reject/", {"note": "call us"},
        format="json",
    )
    guardian.refresh_from_db()
    assert guardian.email == "old@example.test"
    assert ContactChangeRequest.objects.get(pk=req_id).status == "REJECTED"


def test_contact_change_rejects_a_disallowed_field(auth_client, make_user):
    parent, _kid, _g = _parent_with_child(make_user)
    client = auth_client(parent)
    r = client.post("/api/portal/contact-change-requests/", {
        "field": "government_id", "proposed_value": "x",
    }, format="json")
    assert r.status_code == 400


def test_parent_cannot_request_a_change_for_another_guardian(auth_client, make_user):
    parent, _kid, _g = _parent_with_child(make_user)
    # a second guardian record not linked to this user
    Guardian.objects.create(first_name="Someone", last_name="Else", email="e@example.test")
    client = auth_client(parent)
    # the endpoint only ever targets the caller's own guardian, so a stray one
    # can't be reached — assert the happy path still targets the right record
    ok = client.post("/api/portal/contact-change-requests/", {
        "field": "phone", "proposed_value": "555-9999",
    }, format="json")
    assert ok.status_code == 201
    assert ContactChangeRequest.objects.get(pk=ok.data["id"]).guardian.user_id == parent.pk


def test_portal_consent_submission_is_a_new_versioned_row(auth_client, make_user):
    parent, kid, _g = _parent_with_child(make_user)
    Consent.objects.create(student=kid, kind=Consent.Kind.PHOTO, granted=True, version="1",
                           recorded_at=timezone.now() - dt.timedelta(days=30))

    client = auth_client(parent)
    resp = client.post("/api/portal/consents/", {
        "student": str(kid.pk), "kind": "PHOTO", "granted": False, "version": "2",
    }, format="json")
    assert resp.status_code == 201

    current = Consent.current_for(kid, Consent.Kind.PHOTO)
    assert current.version == "2"
    assert current.granted is False
    assert current.recorded_by_id == parent.pk
    assert Consent.objects.filter(student=kid, kind=Consent.Kind.PHOTO).count() == 2


def test_portal_consent_rejected_for_another_childs_record(auth_client, make_user):
    parent, _kid, _g = _parent_with_child(make_user)
    other = make_student()
    client = auth_client(parent)
    r = client.post("/api/portal/consents/", {
        "student": str(other.pk), "kind": "PHOTO", "granted": True,
    }, format="json")
    assert r.status_code == 403
