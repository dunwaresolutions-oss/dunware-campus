from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.audit.models import AuditAction, AuditEntry
from apps.people.models import Student
from apps.people.tests.factories import make_group, make_student
from apps.registration.models import Application, Consent, Enrolment, Offer
from apps.registration.services import convert_application, make_offer, respond_to_offer

pytestmark = pytest.mark.django_db


def _application(**kw) -> Application:
    kw.setdefault("child_first_name", "Prospa")
    kw.setdefault("child_last_name", "Tive")
    kw.setdefault("child_date_of_birth", dt.date(2021, 3, 1))
    kw.setdefault("applicant_name", "A Parent")
    kw.setdefault("applicant_email", "apply@example.test")
    return Application.objects.create(**kw)


def test_full_pipeline_application_to_enrolment(superadmin):
    group = make_group()
    app = _application()

    offer = make_offer(app, group=group, start_date=timezone.localdate(),
                       expires_at=timezone.now() + dt.timedelta(days=7), actor=superadmin)
    app.refresh_from_db()
    assert app.status == Application.Status.OFFER_MADE
    assert offer.is_open

    respond_to_offer(offer, accept=True, actor=superadmin)
    offer.refresh_from_db()
    assert offer.status == Offer.Status.ACCEPTED

    student, enrolment = convert_application(app, group=group, actor=superadmin)
    app.refresh_from_db()
    assert app.status == Application.Status.ENROLLED
    assert app.student_id == student.pk
    assert enrolment.status == Enrolment.Status.ACTIVE
    assert student.status == Student.Status.ENROLLED
    assert AuditEntry.objects.filter(action=AuditAction.ERASE).count() == 0
    assert AuditEntry.objects.filter(
        action=AuditAction.CREATE, object_type="people.Student", object_id=str(student.pk)
    ).exists()


def test_convert_refuses_a_declined_application():
    app = _application(status=Application.Status.DECLINED)
    with pytest.raises(Exception):  # noqa: B017 - DRF ValidationError
        convert_application(app)


def test_active_enrolment_is_unique_per_group():
    from django.db import IntegrityError

    group = make_group()
    student = make_student()
    Enrolment.objects.create(student=student, group=group)
    with pytest.raises(IntegrityError):
        Enrolment.objects.create(student=student, group=group)


def test_consent_versioning_returns_the_latest():
    student = make_student()
    Consent.objects.create(student=student, kind=Consent.Kind.PHOTO, version="1", granted=True,
                           recorded_at=timezone.now() - dt.timedelta(days=10))
    latest = Consent.objects.create(student=student, kind=Consent.Kind.PHOTO, version="2",
                                    granted=False, recorded_at=timezone.now())
    Consent.objects.create(student=student, kind=Consent.Kind.MEDIA, version="1", granted=True)

    current = Consent.current_for(student, Consent.Kind.PHOTO)
    assert current.pk == latest.pk
    assert current.granted is False
