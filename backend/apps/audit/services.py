"""
The one way to write an audit entry.

Usage from a viewset / service:

    from apps.audit.services import record
    record("READ", obj, summary="viewed health record")

Phase 1 adds automatic hooks: a DRF permission mixin that records READ on
retrieve/list of SensitiveModel subclasses, model signals for CRUD, and
login/logout signal handlers.
"""
from __future__ import annotations

from django.db import models

from .middleware import current_actor, current_ip
from .models import AuditEntry


def _object_type(obj) -> str:
    if isinstance(obj, models.Model):
        return f"{obj._meta.app_label}.{obj._meta.object_name}"
    return str(type(obj).__name__)


def record_safe(action: str, obj=None, **kwargs):
    """``record()`` that never propagates. For logging / guard / exception-handler
    paths where a failed audit write must not become the response the caller
    sees. Returns the entry, or ``None`` if the write failed."""
    try:
        return record(action, obj, **kwargs)
    except Exception:  # noqa: BLE001 - deliberate: a failed audit write must not become the response
        return None


def record(
    action: str,
    obj=None,
    *,
    summary: str = "",
    changed_fields: list[str] | None = None,
    actor=None,
    extra: dict | None = None,
) -> AuditEntry:
    actor = actor or current_actor()
    if actor is not None:
        label = getattr(actor, "get_full_name", lambda: "")() or getattr(actor, "username", "")
    else:
        label = "system"
    return AuditEntry.objects.create(
        actor=actor if isinstance(actor, models.Model) else None,
        actor_label=label,
        actor_role=getattr(actor, "role", "") or "",
        source_ip=current_ip(),
        action=action,
        object_type=_object_type(obj) if obj is not None else "",
        object_id=str(getattr(obj, "pk", "")) if obj is not None else "",
        summary=summary[:255],
        changed_fields=changed_fields or [],
        extra=extra or {},
    )
