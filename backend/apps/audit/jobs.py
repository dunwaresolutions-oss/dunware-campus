"""
Scheduled maintenance for the audit log (django-q2, wired in Phase 8).

The audit log is retained long (``RETENTION_AUDIT_LOG_DAYS``, default 10 years)
and is append-only, so "retention" here means **anonymize, never delete**:
entries older than the window keep their action/object/time but lose the actor
back-reference and source IP. A separate, deliberately manual purge exists for
the rare legal instruction to remove entries entirely — it is not scheduled.
"""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import AuditEntry


def anonymize_expired_audit_entries(now=None) -> int:
    """Blank the actor FK and source IP on entries past the retention window.
    Returns the number of rows touched. Safe to run repeatedly."""
    now = now or timezone.now()
    days = int(getattr(settings, "RETENTION_AUDIT_LOG_DAYS", 3650))
    cutoff = now - timedelta(days=days)
    stale = AuditEntry.all_objects.filter(at__lt=cutoff).exclude(
        actor__isnull=True, source_ip__isnull=True
    )
    return stale.update(actor=None, source_ip=None)


def audit_retention_sweep() -> dict:
    """Entry point for the scheduled task (Phase 8 registers it with django-q2)."""
    touched = anonymize_expired_audit_entries()
    return {"anonymized": touched}
