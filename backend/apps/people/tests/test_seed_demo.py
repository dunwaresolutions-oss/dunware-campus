"""seed_demo — the synthetic dataset must leave no console section empty."""
from __future__ import annotations

import pytest
from django.apps import apps as django_apps
from django.core.management import call_command

pytestmark = pytest.mark.django_db

# every operational table the demo is expected to populate.
EXPECT_NONEMPTY = [
    "accounts.User",
    "core.SchoolProfile",
    "scheduling.AcademicYear", "scheduling.Term", "scheduling.Room",
    "scheduling.Closure", "scheduling.SessionTemplate", "scheduling.SessionOccurrence",
    "people.Group", "people.GroupStaff", "people.Student", "people.Guardian",
    "people.GuardianLink", "people.EmergencyContact", "people.AuthorizedPickup",
    "people.Observation", "people.Document", "people.ContactChangeRequest",
    "registration.Enrolment", "registration.Application", "registration.Consent",
    "registration.WaitlistEntry", "registration.Offer",
    "registration.ApplicationDocument",
    "health.HealthProfile", "health.Allergy", "health.Condition",
    "health.Medication", "health.ActionPlan", "health.HealthAccessGrant",
    "attendance.AttendanceRecord",
    "lessons.CurriculumUnit", "lessons.LessonPlan", "lessons.LessonResource",
    "grades.AssessmentScheme", "grades.RubricCriterion", "grades.Assessment",
    "grades.AssessmentResult", "grades.RubricScore",
    "grades.ReportCard", "grades.ReportCardEntry",
    "communication.Announcement", "communication.MessageThread",
    "communication.Message", "communication.MessageTemplate",
    "communication.IncidentReport",
    "communication.IncidentAcknowledgement", "communication.OutboundEmail",
    "billing.FeeSchedule", "billing.Invoice", "billing.InvoiceLine",
    "billing.Payment", "billing.Credit",
    "booking.Offering", "booking.AvailabilityWindow", "booking.Slot",
    "booking.Booking",
    "audit.AuditEntry",
    "reporting.BackupRun",
]


def _empty(labels):
    out = []
    for lbl in labels:
        model = django_apps.get_model(*lbl.split("."))
        if not model.objects.exists():
            out.append(lbl)
    return out


def test_quick_seed_fills_every_section():
    call_command("seed_demo", "--quick", "--force")
    assert _empty(EXPECT_NONEMPTY) == []


def test_flush_then_reseed_is_clean():
    call_command("seed_demo", "--quick", "--force")
    call_command("seed_demo", "--quick", "--force", "--flush")
    assert _empty(EXPECT_NONEMPTY) == []


def test_status_variety_is_present():
    call_command("seed_demo", "--quick", "--force")
    from apps.billing.models import Invoice
    from apps.communication.models import IncidentReport
    from apps.grades.models import ReportCard
    from apps.registration.models import Application

    assert {"SUBMITTED", "UNDER_REVIEW", "WAITLISTED"} <= set(
        Application.objects.values_list("status", flat=True)
    )
    assert {"DRAFT", "FINALIZED", "RELEASED"} <= set(
        ReportCard.objects.values_list("status", flat=True)
    )
    assert {"DRAFT", "SENT"} <= set(
        IncidentReport.objects.values_list("status", flat=True)
    )
    assert {"DRAFT", "ISSUED"} <= set(
        Invoice.objects.values_list("status", flat=True)
    )
