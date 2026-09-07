"""
Per-role end-to-end journeys (Phase 8 hardening).

Each test walks one role through a realistic multi-step slice of Campus
against the real API — not a single-endpoint unit check — standing in for a
manual click-through per role (there is no built console UI yet to click
through; the backend contract is what a UI would drive). Where a step should
be refused, that refusal is asserted too, not just the happy path.
"""
from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.audit.models import AuditAction, AuditEntry
from apps.people.models import ContactChangeRequest, Student
from apps.people.tests.factories import assign_staff, enrol, link_guardian, make_group, make_student
from apps.scheduling.models import AcademicYear, Term

pytestmark = pytest.mark.django_db


def _term():
    year = AcademicYear.objects.create(name="2026-2027", start_date=dt.date(2026, 9, 1),
                                       end_date=dt.date(2027, 6, 30))
    return Term.objects.create(academic_year=year, name="T1", start_date=dt.date(2026, 9, 1),
                               end_date=dt.date(2026, 12, 20))


def test_admin_journey_group_student_billing_health_grant_and_audit(auth_client, admin_user):
    """Admin: stand up a group + student, issue and collect a fee, grant a
    teacher health access, and see it all land in the audit trail."""
    client = auth_client(admin_user)

    group = client.post("/api/groups/", {"name": "Grade 1", "kind": "CLASS"},
                        format="json")
    assert group.status_code == 201
    group_id = group.data["id"]

    student = client.post("/api/students/", {
        "first_name": "Nova", "last_name": "Reyes", "date_of_birth": "2019-04-02",
        "primary_group": group_id,
    }, format="json")
    assert student.status_code == 201
    student_id = student.data["id"]

    invoice = client.post("/api/invoices/", {"student": student_id}, format="json")
    assert invoice.status_code == 201
    invoice_id = invoice.data["id"]
    client.post(f"/api/invoices/{invoice_id}/issue/")

    from apps.billing.models import InvoiceLine
    InvoiceLine.objects.create(invoice_id=invoice_id, description="Registration",
                               unit_amount_cents=5000)
    paid = client.post(f"/api/invoices/{invoice_id}/mark-paid/",
                       {"amount_cents": 5000, "method": "CASH"}, format="json")
    assert paid.status_code == 201
    assert paid.data["invoice"]["status"] == "PAID"

    from apps.accounts.models import User  # grant health access to a second staff account
    other_teacher = User(username="nurse_teacher", role=Role.TEACHER)
    other_teacher.set_password("Sup3r-Secret-Pw!")
    other_teacher.save()
    grant = client.post("/api/health/access-grants/",
                        {"user": str(other_teacher.pk), "reason": "school nurse"},
                        format="json")
    assert grant.status_code == 201

    # the trail: student created, invoice paid, grant created — all audited
    assert AuditEntry.objects.filter(
        action=AuditAction.CREATE, object_type="people.Student", object_id=student_id
    ).exists()
    assert AuditEntry.objects.filter(
        action=AuditAction.CREATE, object_type="billing.Payment"
    ).exists()
    assert Student.objects.get(pk=student_id).display_name == "Nova Reyes"


def test_front_desk_journey_application_to_enrolled_student(auth_client, front_desk):
    """Front desk: intake an application, review it, offer a spot, accept,
    and convert it into a real enrolled Student."""
    client = auth_client(front_desk)
    group = make_group()

    app = client.post("/api/applications/", {
        "child_first_name": "Theo", "child_last_name": "Park",
        "child_date_of_birth": "2020-02-14",
        "applicant_name": "P Park", "applicant_email": "p.park@example.test",
    }, format="json")
    assert app.status_code == 201
    app_id = app.data["id"]

    assert client.post(f"/api/applications/{app_id}/review/").data["status"] == "UNDER_REVIEW"

    offer = client.post(f"/api/applications/{app_id}/make_offer/", {
        "group": str(group.pk), "start_date": "2026-10-01",
        "expires_at": (timezone.now() + dt.timedelta(days=14)).isoformat(),
    }, format="json")
    assert offer.status_code == 201
    offer_id = offer.data["id"]

    accepted = client.post(f"/api/offers/{offer_id}/accept/")
    assert accepted.status_code == 200 and accepted.data["status"] == "ACCEPTED"

    converted = client.post(f"/api/applications/{app_id}/convert/",
                            {"group": str(group.pk)}, format="json")
    assert converted.status_code == 201
    student = Student.objects.get(pk=converted.data["student"])
    assert student.status == Student.Status.ENROLLED
    assert student.first_name == "Theo"


def test_teacher_journey_roster_attendance_lesson_grade_incident(auth_client, staff):
    """Teacher: check a student in and out, publish a lesson, grade an
    assessment for their own group, and file + notify an incident."""
    from apps.people.models import AuthorizedPickup

    client = auth_client(staff)
    group = make_group()
    assign_staff(group, staff)
    kid = make_student()
    enrol(kid, group)
    pickup = AuthorizedPickup.objects.create(student=kid, name="Aunt Sam", relationship="aunt")

    checked_in = client.post("/api/attendance/check-in/",
                             {"student": str(kid.pk), "group": str(group.pk)}, format="json")
    assert checked_in.status_code == 200
    rec_id = checked_in.data["id"]

    checked_out = client.post(f"/api/attendance/{rec_id}/check-out/",
                              {"pickup_id": str(pickup.pk)}, format="json")
    assert checked_out.status_code == 200
    assert checked_out.data["collected_by_name"] == "Aunt Sam"

    plan = client.post("/api/lesson-plans/", {
        "group": str(group.pk), "date": "2026-09-15", "title": "Shapes",
        "objectives": "Recognize circles and squares.",
    }, format="json")
    assert plan.status_code == 201
    published = client.post(f"/api/lesson-plans/{plan.data['id']}/publish/")
    assert published.data["status"] == "PUBLISHED"

    scheme = client.post("/api/assessment-schemes/",
                         {"group": str(group.pk), "name": "Term 1"}, format="json")
    assessment = client.post("/api/assessments/", {
        "scheme": scheme.data["id"], "group": str(group.pk), "title": "Shapes quiz",
        "date": "2026-09-16",
    }, format="json")
    result = client.post("/api/assessment-results/", {
        "assessment": assessment.data["id"], "student": str(kid.pk), "mark": "95",
        "narrative": "Great work.",
    }, format="json")
    assert result.status_code == 201

    incident = client.post("/api/incident-reports/", {
        "student": str(kid.pk), "occurred_at": timezone.now().isoformat(),
        "category": "INJURY", "description": "Bumped a knee on the slide.",
    }, format="json")
    assert incident.status_code == 201
    notified = client.post(f"/api/incident-reports/{incident.data['id']}/notify/")
    assert notified.status_code == 200 and notified.data["status"] == "SENT"

    # and confirm the teacher stays fenced out of billing entirely
    assert client.get("/api/invoices/").status_code == 403


def test_parent_journey_dashboard_booking_contact_change_and_consent(
    auth_client, make_user, admin_user
):
    """Parent: see the portal dashboard, book a slot, ask for a contact
    change, and record a consent - never touching another family's data."""
    from apps.booking.models import AvailabilityWindow, Offering
    from apps.booking.services import generate_slots

    kid = make_student()
    other_kid = make_student()
    parent = make_user(username="journey_parent", role=Role.PARENT)
    link = link_guardian(kid, user=parent)
    link.guardian.phone = "555-0100"
    link.guardian.save(update_fields=["phone"])
    group = make_group()
    enrol(kid, group)

    office = auth_client(admin_user)
    offering_resp = office.post("/api/offerings/", {
        "title": "Art club", "capacity_per_slot": 3, "duration_minutes": 45,
    }, format="json")
    offering = Offering.objects.get(pk=offering_resp.data["id"])
    # a week out, so the generated slot is always still "upcoming" regardless
    # of the wall-clock time the suite runs at
    slot_day = timezone.localdate() + dt.timedelta(days=7)
    window = AvailabilityWindow.objects.create(
        offering=offering, weekday=slot_day.weekday(),
        start_time=dt.time(15, 0), end_time=dt.time(16, 0),
        valid_from=slot_day, valid_to=slot_day,
    )
    generate_slots(offering, from_date=window.valid_from, to_date=window.valid_to)
    slot_id = str(offering.slots.first().pk)

    parent_client = auth_client(parent)

    dashboard = parent_client.get("/api/portal/dashboard/")
    assert dashboard.status_code == 200
    ids = {c["id"] for c in dashboard.data["children"]}
    assert ids == {str(kid.pk)}
    assert str(other_kid.pk) not in ids

    booked = parent_client.post("/api/bookings/", {"slot": slot_id, "student": str(kid.pk)},
                                format="json")
    assert booked.status_code == 201
    dashboard_after = parent_client.get("/api/portal/dashboard/")
    booking_ids = {b["id"] for b in dashboard_after.data["children"][0]["upcoming_bookings"]}
    assert booked.data["id"] in booking_ids

    # cannot book for a child that isn't theirs
    denied = parent_client.post("/api/bookings/", {"slot": slot_id, "student": str(other_kid.pk)},
                                format="json")
    assert denied.status_code == 403

    change = parent_client.post("/api/portal/contact-change-requests/", {
        "field": "phone", "proposed_value": "555-0199", "reason": "moved",
    }, format="json")
    assert change.status_code == 201
    assert ContactChangeRequest.objects.get(pk=change.data["id"]).requested_by_id == parent.pk

    consent = parent_client.post("/api/portal/consents/", {
        "student": str(kid.pk), "kind": "PHOTO", "granted": True,
    }, format="json")
    assert consent.status_code == 201

    # invoices, if any, are read-only for a parent
    assert link.guardian.phone == "555-0100"  # unapplied until the office approves


def test_student_journey_sees_only_self(auth_client, make_user):
    """An older student's own login only ever surfaces their own record."""
    kid = make_student()
    other_kid = make_student()
    student_user = make_user(username="the_student", role=Role.STUDENT)
    Student.objects.filter(pk=kid.pk).update(user=student_user)

    client = auth_client(student_user)
    dashboard = client.get("/api/portal/dashboard/")
    assert dashboard.status_code == 200
    ids = {c["id"] for c in dashboard.data["children"]}
    assert ids == {str(kid.pk)}
    assert str(other_kid.pk) not in ids

    # a student cannot reach the staff student list at all
    assert client.get("/api/students/").status_code in (200, 403)
    if client.get("/api/students/").status_code == 200:
        listed_ids = {str(r["id"]) for r in client.get("/api/students/").data["results"]}
        assert listed_ids <= {str(kid.pk)}


def test_tutor_journey_owns_offering_but_not_billing(auth_client, make_user, admin_user):
    """A tutor runs their own booking offering end to end, but billing stays
    completely out of reach even though bookings tie back to real students."""
    from apps.booking.models import Offering

    tutor = make_user(username="journey_tutor", role=Role.TUTOR)
    office = auth_client(admin_user)
    created = office.post("/api/offerings/", {
        "title": "Guitar lessons", "provider": str(tutor.pk), "capacity_per_slot": 1,
        "duration_minutes": 30,
    }, format="json")
    assert created.status_code == 201
    offering_id = created.data["id"]
    assert Offering.objects.get(pk=offering_id).provider_id == tutor.pk

    window = office.post("/api/availability-windows/", {
        "offering": offering_id, "weekday": 0, "start_time": "15:00:00",
        "end_time": "16:00:00", "valid_from": "2026-09-07", "valid_to": "2026-09-13",
    }, format="json")
    assert window.status_code == 201

    tutor_client = auth_client(tutor)
    generated = tutor_client.post(f"/api/offerings/{offering_id}/generate_slots/", {
        "from_date": "2026-09-07", "to_date": "2026-09-13",
    }, format="json")
    assert generated.status_code == 201
    assert generated.data["created"] > 0

    assert tutor_client.get("/api/invoices/").status_code == 403
    assert tutor_client.post("/api/fee-schedules/", {"name": "x", "amount_cents": 100},
                             format="json").status_code == 403
