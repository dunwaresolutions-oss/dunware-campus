"""
Staff intranet chat/alert system — direct messages and role broadcasts between
staff accounts (teacher, tutor, front desk, admin, superadmin). Never reaches
parent/student portals and never leaves the LAN (plain polling over the same
API, no external transport).

Bodies routinely name a student ("Jordan P. will be late, held at front
office") so this is a ``SensitiveModel`` — reads are audited like any other
record that can carry a child's name in free text.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.accounts.models import Role
from apps.core.fields import EncryptedTextField
from apps.core.models import BaseModel, SensitiveModel

_ADMIN_ROLES = frozenset({Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK})


class StaffMessage(SensitiveModel):
    """One direct message or one role broadcast. Broadcasts have
    ``recipient=None`` and an ``audience`` other than ``DIRECT``; only
    front-office roles may send those (enforced in the view, not here, so a
    data migration/fixture can still seed one without a request in flight)."""

    PII_FIELDS = ("body",)

    class Audience(models.TextChoices):
        DIRECT = "DIRECT", "Direct message"
        TEACHERS = "TEACHERS", "All teachers"
        TUTORS = "TUTORS", "All tutors"
        ALL_STAFF = "ALL_STAFF", "All staff"

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="Null for a role broadcast.",
    )
    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.DIRECT)
    body = EncryptedTextField()
    urgent = models.BooleanField(default=False)

    class Meta:
        db_table = "staffchat_message"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "created_at"]),
            models.Index(fields=["audience", "created_at"]),
        ]

    def __str__(self) -> str:
        target = self.recipient_id or self.audience
        return f"staff message from {self.sender_id} to {target}"

    def is_visible_to(self, user) -> bool:
        role = getattr(user, "role", None)
        if role in _ADMIN_ROLES:
            return True
        if self.sender_id == user.pk or self.recipient_id == user.pk:
            return True
        if self.audience == self.Audience.ALL_STAFF:
            return True
        if self.audience == self.Audience.TEACHERS and role == Role.TEACHER:
            return True
        if self.audience == self.Audience.TUTORS and role == Role.TUTOR:
            return True
        return False


class StaffChatCursor(BaseModel):
    """Per-user watermark: messages addressed to this user created after
    ``last_read_at`` are unread. One row per staff account, created on first
    use rather than by a signal/migration."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staffchat_cursor"
    )
    last_read_at = models.DateTimeField()

    class Meta:
        db_table = "staffchat_cursor"

    def __str__(self) -> str:
        return f"cursor for {self.user_id} @ {self.last_read_at}"
