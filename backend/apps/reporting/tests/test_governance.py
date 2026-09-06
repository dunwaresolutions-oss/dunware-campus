from __future__ import annotations

import datetime as dt

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.audit.models import AuditAction, AuditEntry
from apps.health.models import Allergy, HealthProfile
from apps.people.models import Student
from apps.people.tests.factories import link_guardian, make_student
from apps.registration.models import Consent
from apps.reporting.services import LegalHoldError, data_subject_export, erase_person

pytestmark = pytest.mark.django_db


def _rich_student() -> Student:
    s = make_student(government_id="AAA-111", custody_notes="mother has custody")
    link_guardian(s, first_name="Dana", email="dana@example.test")
    HealthProfile.objects.create(student=s, notes="wears glasses")
    Allergy.objects.create(student=s, allergen="dairy", reaction="rash",
                           severity=Allergy.Severity.MODERATE)
    Consent.objects.create(student=s, kind=Consent.Kind.PHOTO, granted=True,
                           granted_by_name="Dana")
    return s


def test_data_subject_export_is_complete_and_decrypted(superadmin):
    s = _rich_student()
    data = data_subject_export(s, actor=superadmin)

    assert data["student"]["government_id"] == "AAA-111"
    assert data["student"]["custody_notes"] == "mother has custody"
    assert data["guardians"][0]["email"] == "dana@example.test"
    assert data["health"]["allergies"][0]["allergen"] == "dairy"
    assert data["health"]["profile"]["notes"] == "wears glasses"
    assert data["consents"][0]["kind"] == "PHOTO"
    assert AuditEntry.objects.filter(
        action=AuditAction.EXPORT, object_id=str(s.pk)
    ).exists()


def test_erase_person_anonymizes_and_removes_health(superadmin):
    s = _rich_student()
    result = erase_person(s, actor=superadmin, reason="parent request")
    s.refresh_from_db()

    assert s.first_name == "ERASED" and s.last_name == "ERASED"
    assert s.government_id == "" and s.custody_notes == ""
    assert s.anonymized_at is not None and s.deleted_at is not None
    assert Allergy.objects.filter(student=s).count() == 0
    assert HealthProfile.objects.filter(student=s).count() == 0
    assert result["removed"]["allergies"] == 1
    assert AuditEntry.objects.filter(action=AuditAction.ERASE, object_id=str(s.pk)).exists()


def test_erase_person_blocked_by_legal_hold(superadmin):
    s = make_student(legal_hold=True)
    with pytest.raises(LegalHoldError):
        erase_person(s, actor=superadmin)
    s.refresh_from_db()
    assert s.first_name != "ERASED"


def test_retention_sweep_anonymizes_old_leavers_but_not_recent_or_held(superadmin, settings):
    settings.RETENTION_PAST_STUDENT_DAYS = 365
    old = timezone.localdate() - dt.timedelta(days=400)
    recent = timezone.localdate() - dt.timedelta(days=10)

    stale = make_student(status=Student.Status.WITHDRAWN, left_on=old)
    fresh = make_student(status=Student.Status.WITHDRAWN, left_on=recent)
    held = make_student(status=Student.Status.GRADUATED, left_on=old, legal_hold=True)

    call_command("run_retention")  # smoke: the command runs end to end
    stale.refresh_from_db()
    fresh.refresh_from_db()
    held.refresh_from_db()

    assert stale.anonymized_at is not None
    assert fresh.anonymized_at is None
    assert held.anonymized_at is None


def test_seed_demo_builds_a_graph():
    call_command("seed_demo", quick=True, seed=7, force=True)
    from apps.people.models import Group, Guardian
    from apps.scheduling.models import Closure, Term

    assert Student.objects.count() >= 6
    assert Group.objects.filter(kind=Group.Kind.CLASS).count() == 6  # quick = 6 grades x 1
    assert Guardian.objects.exists()
    assert Term.objects.count() == 2
    assert Closure.objects.exists()          # holidays + breaks seeded
    from apps.grades.models import ReportCard

    assert ReportCard.objects.filter(status=ReportCard.Status.RELEASED).exists()


def test_seed_demo_flush_then_reseed_is_idempotent():
    call_command("seed_demo", quick=True, seed=1, force=True)
    first = Student.objects.count()
    call_command("seed_demo", quick=True, seed=1, force=True, flush=True)
    assert Student.objects.count() == first   # replaced, not stacked


def test_seed_demo_refuses_without_debug(settings):
    settings.DEBUG = False
    with pytest.raises(Exception):  # noqa: B017 - CommandError
        call_command("seed_demo", students=2)
