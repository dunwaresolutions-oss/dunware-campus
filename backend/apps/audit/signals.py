"""
Automatic write-auditing for registered models (see registry.py).

``post_save`` / ``post_delete`` receivers turn a persisted change into an
``AuditEntry`` through the one sanctioned path, ``services.record``. Reads are
handled separately by ``apps.audit.mixins.AuditReadMixin`` because only the API
layer knows a retrieve/list actually disclosed data.

Field-level change detection here is deliberately shallow: we record the
*names* passed in ``update_fields`` when the caller supplies them. Feature apps
that need a full before/after field list use an explicit ``record(... ,
changed_fields=[...])`` in their service layer.
"""
from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import AuditAction, AuditEntry
from .registry import is_audited
from .services import record


def _should_skip(sender, instance, raw: bool) -> bool:
    if raw:  # loaddata / fixtures
        return True
    if sender is AuditEntry:  # never audit the audit log
        return True
    return not is_audited(sender)


@receiver(post_save, dispatch_uid="audit_post_save")
def _audit_post_save(sender, instance, created, raw=False, update_fields=None, **kwargs):
    if _should_skip(sender, instance, raw):
        return
    action = AuditAction.CREATE if created else AuditAction.UPDATE
    changed = sorted(update_fields) if update_fields else []
    record(
        action,
        instance,
        summary=f"{'created' if created else 'updated'} {instance._meta.verbose_name}",
        changed_fields=changed,
    )


@receiver(post_delete, dispatch_uid="audit_post_delete")
def _audit_post_delete(sender, instance, **kwargs):
    if _should_skip(sender, instance, raw=False):
        return
    record(
        AuditAction.DELETE,
        instance,
        summary=f"deleted {instance._meta.verbose_name}",
    )
