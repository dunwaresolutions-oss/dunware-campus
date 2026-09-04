"""
Append-only audit log (see docs/PII_SECURITY.md).

Every create / update / delete AND every *read* of a sensitive record is
recorded here: who, what action, which object, when, from where. Entries
reference object type + id — never field values. The model is append-only:
no update/delete path exists in the app, and the retention job only ever
*adds* an anonymization marker, it does not rewrite history.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    CREATE = "CREATE", "Create"
    READ = "READ", "Read"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"
    LOGIN = "LOGIN", "Login"
    LOGIN_FAILED = "LOGIN_FAILED", "Login failed"
    LOGOUT = "LOGOUT", "Logout"
    EXPORT = "EXPORT", "Data export"
    ERASE = "ERASE", "Erasure"
    PERMISSION_DENIED = "PERMISSION_DENIED", "Permission denied"


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

    class Meta:
        db_table = "audit_entry"
        indexes = [
            models.Index(fields=["object_type", "object_id", "at"]),
            models.Index(fields=["actor", "at"]),
        ]
        # append-only: no default manager method removes rows; enforced in code review + CI

    def __str__(self) -> str:
        who = self.actor_label or "system"
        return f"{self.at:%Y-%m-%d %H:%M} {who} {self.action} {self.object_type}#{self.object_id}"
