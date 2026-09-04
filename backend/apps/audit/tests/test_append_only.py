"""The audit log is append-only; retention may only anonymize."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.audit.jobs import anonymize_expired_audit_entries
from apps.audit.models import AuditAction, AuditEntry
from apps.audit.services import record

pytestmark = pytest.mark.django_db


def test_existing_entry_cannot_be_saved_again():
    entry = record(AuditAction.READ, summary="viewed something")
    entry.summary = "rewritten"
    with pytest.raises(IntegrityError):
        entry.save()


def test_queryset_update_is_blocked():
    record(AuditAction.READ, summary="x")
    with pytest.raises(IntegrityError):
        AuditEntry.objects.update(summary="nope")


def test_delete_is_blocked_on_instance_and_queryset():
    entry = record(AuditAction.READ, summary="x")
    with pytest.raises(IntegrityError):
        entry.delete()
    with pytest.raises(IntegrityError):
        AuditEntry.objects.all().delete()


def test_retention_anonymizes_old_entries_without_losing_history(superadmin):
    entry = record(AuditAction.LOGIN, summary="old login", actor=superadmin)
    AuditEntry.all_objects.filter(pk=entry.pk).update(
        at=timezone.now() - timedelta(days=40_000), source_ip="10.1.2.3"
    )

    touched = anonymize_expired_audit_entries()
    assert touched == 1

    entry.refresh_from_db()
    assert entry.actor_id is None
    assert entry.source_ip is None
    assert entry.action == AuditAction.LOGIN
    assert entry.summary == "old login"


def test_retention_is_idempotent_and_leaves_recent_entries_alone(superadmin):
    recent = record(AuditAction.LOGIN, summary="recent", actor=superadmin)
    assert anonymize_expired_audit_entries() == 0
    recent.refresh_from_db()
    assert recent.actor_id == superadmin.pk
