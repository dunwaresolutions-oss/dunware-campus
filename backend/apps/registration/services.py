"""
Registration lifecycle operations. Kept out of the viewset so the same steps
are callable from the admin, a management command, or a future portal flow —
and so each writes its own audit trail.
"""
from __future__ import annotations

import secrets

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.people.models import Student

from .models import Application, Enrolment, Offer


def _student_number() -> str:
    for _ in range(10):
        candidate = f"S{secrets.randbelow(9_000_000) + 1_000_000}"
        if not Student.objects.filter(student_number=candidate).exists():
            return candidate
    raise RuntimeError("could not allocate a unique student number")  # pragma: no cover


@transaction.atomic
def convert_application(application: Application, *, group=None, start_date=None, actor=None):
    """Turn a reviewed application into a real Student (+ an Enrolment when a
    group is known). Idempotent-ish: refuses if already linked to a student."""
    if application.student_id:
        raise ValidationError("This application already has a student record.")
    is_closed = (
        application.status in Application.TERMINAL
        and application.status != Application.Status.ENROLLED
    )
    if is_closed:
        raise ValidationError(f"Application is {application.status}; cannot convert.")

    student = Student.objects.create(
        first_name=application.child_first_name,
        last_name=application.child_last_name,
        date_of_birth=application.child_date_of_birth,
        student_number=_student_number(),
        status=Student.Status.ENROLLED if group else Student.Status.PROSPECTIVE,
        primary_group=group,
    )
    application.student = student
    application.status = Application.Status.ENROLLED if group else Application.Status.UNDER_REVIEW
    application.save(update_fields=["student", "status", "updated_at"])
    record(AuditAction.CREATE, student,
           summary=f"student created from application {application.pk}", actor=actor)

    enrolment = None
    if group is not None:
        enrolment = Enrolment.objects.create(
            student=student, group=group,
            start_date=start_date or timezone.localdate(),
            source_application=application,
        )
    return student, enrolment


def make_offer(application: Application, *, group, start_date, expires_at, actor=None) -> Offer:
    offer = Offer.objects.create(
        application=application, group=group, start_date=start_date,
        expires_at=expires_at, made_by=actor if getattr(actor, "pk", None) else None,
    )
    offer.refresh_from_db()  # normalize any string date/datetime the caller passed
    application.status = Application.Status.OFFER_MADE
    application.save(update_fields=["status", "updated_at"])
    record(AuditAction.UPDATE, application, summary="offer made", actor=actor)
    return offer


def respond_to_offer(offer: Offer, *, accept: bool, actor=None) -> Offer:
    if offer.status != Offer.Status.PENDING:
        raise ValidationError(f"Offer is already {offer.status}.")
    offer.status = Offer.Status.ACCEPTED if accept else Offer.Status.DECLINED
    offer.responded_at = timezone.now()
    offer.save(update_fields=["status", "responded_at"])
    if not accept:
        offer.application.status = Application.Status.DECLINED
        offer.application.save(update_fields=["status", "updated_at"])
    record(AuditAction.UPDATE, offer,
           summary=f"offer {'accepted' if accept else 'declined'}", actor=actor)
    return offer
