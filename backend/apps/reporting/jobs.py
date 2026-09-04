"""
Scheduled data-governance jobs (django-q2 registers ``retention_sweep`` in
Phase 8; until then run it with ``manage.py run_retention``).

- audit-log anonymization (from apps.audit.jobs)
- students left more than ``RETENTION_PAST_STUDENT_DAYS`` ago, not on legal
  hold, not already anonymized -> erase_person()
- applications in a terminal state older than the same window -> soft-deleted

Everything it touches is audited by the underlying service / signal.
"""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.audit.jobs import audit_retention_sweep


def _cutoff(days_setting: str, default: int):
    days = int(getattr(settings, days_setting, default))
    return timezone.localdate() - timedelta(days=days), days


def sweep_past_students(now=None) -> int:
    from apps.people.models import Student

    from .services import LegalHoldError, erase_person

    cutoff, _ = _cutoff("RETENTION_PAST_STUDENT_DAYS", 2555)
    stale = Student.objects.filter(
        status__in=[Student.Status.WITHDRAWN, Student.Status.GRADUATED],
        left_on__lt=cutoff,
        legal_hold=False,
        anonymized_at__isnull=True,
    )
    done = 0
    for student in stale:
        try:
            erase_person(student, reason="retention window elapsed")
            done += 1
        except LegalHoldError:  # pragma: no cover - filtered out above, defensive
            continue
    return done


def purge_terminal_applications(now=None) -> int:
    from apps.registration.models import Application

    cutoff, _ = _cutoff("RETENTION_PAST_STUDENT_DAYS", 2555)
    stale = Application.objects.alive().filter(
        status__in=list(Application.TERMINAL), submitted_at__date__lt=cutoff
    )
    count = 0
    for app in stale:
        app.notes = ""
        app.applicant_phone = ""
        app.soft_delete()
        count += 1
    return count


def retention_sweep() -> dict:
    return {
        "audit": audit_retention_sweep(),
        "students_erased": sweep_past_students(),
        "applications_purged": purge_terminal_applications(),
    }
