"""
Append-only audit log (see docs/PII_SECURITY.md).

Every create / update / delete AND every *read* of a sensitive record is
recorded here: who, what action, which object, when, from where. Entries
reference object type + id — never field values.

Append-only is enforced three ways:

* the model's ``save()`` refuses to write an existing row and ``delete()``
  always raises;
* the default manager's querysets refuse ``.update()`` / ``.delete()``;
* the admin registration is read-only (``apps/audit/admin.py``).

The only sanctioned mutation is the retention job's anonymization pass, which
goes through the unrestricted ``all_objects`` manager and only ever nulls the
actor back-reference + source IP on entries past the retention window. A
DB-level trigger is added in Phase 8 hardening.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import IntegrityError, models


class AuditAction(models.TextChoices):
    CREATE = "CREATE", "Create"
    READ = "READ", "Read"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"
    LOGIN = "LOGIN", "Login"
    LOGIN_FAILED = "LOGIN_FAILED", "Login failed"
    LOGOUT = "LOGOUT", "Logout"
    LOCKOUT = "LOCKOUT", "Lockout"
    MFA_ENROLLED = "MFA_ENROLLED", "MFA enrolled"
    MFA_VERIFIED = "MFA_VERIFIED", "MFA verified"
    EXPORT = "EXPORT", "Data export"
    ERASE = "ERASE", "Erasure"
    PERMISSION_DENIED = "PERMISSION_DENIED", "Permission denied"


class _AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise IntegrityError("AuditEntry is append-only; use the retention job to anonymize.")

    def delete(self):
        raise IntegrityError("AuditEntry is append-only; entries cannot be deleted.")

    def _raw_delete(self, using):  # pragma: no cover - defensive
        raise IntegrityError("AuditEntry is append-only; entries cannot be deleted.")


class _AppendOnlyManager(models.Manager.from_queryset(_AppendOnlyQuerySet)):
    pass


class AuditEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    actor_label = models.CharField(max_length=150, blank=True)  # snapshot, survives actor deletion
    actor_role = models.CharField(max_length=16, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)

    action = models.CharField(max_length=20, choices=AuditAction.choices, db_index=True)
    object_type = models.CharField(max_length=100, blank=True, db_index=True)   # app_label.Model
    object_id = models.CharField(max_length=64, blank=True, db_index=True)
    summary = models.CharField(max_length=255, blank=True)   # e.g. "viewed health record"
    changed_fields = models.JSONField(default=list, blank=True)  # names only, never values
    extra = models.JSONField(default=dict, blank=True)

    objects = _AppendOnlyManager()
    # retention job only — the one manager allowed to anonymize old rows
    all_objects = models.Manager()  # noqa: DJ012

    class Meta:
        db_table = "audit_entry"
        default_manager_name = "objects"
        indexes = [
            models.Index(fields=["object_type", "object_id", "at"]),
            models.Index(fields=["actor", "at"]),
            models.Index(fields=["action", "at"]),
        ]

    def __str__(self) -> str:
        who = self.actor_label or "system"
        return f"{self.at:%Y-%m-%d %H:%M} {who} {self.action} {self.object_type}#{self.object_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise IntegrityError("AuditEntry is append-only; an existing entry cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise IntegrityError("AuditEntry is append-only; entries cannot be deleted.")
