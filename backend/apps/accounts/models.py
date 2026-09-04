"""
Campus user model.

One user table, an explicit ``role``, and (for portal users) links to the
people they may see. MFA is TOTP via django-otp; staff roles require it
(enforced in Phase 1). Passwords are Argon2 (settings.PASSWORD_HASHERS).
"""
from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    SUPERADMIN = "SUPERADMIN", "Superadmin"
    ADMIN = "ADMIN", "Admin / director"
    TEACHER = "TEACHER", "Teacher / educator"
    TUTOR = "TUTOR", "Tutor / activity lead"
    FRONT_DESK = "FRONT_DESK", "Front desk"
    PARENT = "PARENT", "Parent / guardian"
    STUDENT = "STUDENT", "Student"


STAFF_ROLES = frozenset(
    {Role.SUPERADMIN, Role.ADMIN, Role.TEACHER, Role.TUTOR, Role.FRONT_DESK}
)
PORTAL_ROLES = frozenset({Role.PARENT, Role.STUDENT})


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.FRONT_DESK)
    must_use_mfa = models.BooleanField(
        default=True,
        help_text="Staff roles require TOTP. Portal users may opt in.",
    )
    last_password_change = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_user"

    def save(self, *args, **kwargs):
        # Portal users are not Django "staff"; superadmin maps to is_superuser.
        self.is_staff = self.role in STAFF_ROLES or self.is_superuser
        if self.role == Role.SUPERADMIN:
            self.is_superuser = True
        self.must_use_mfa = self.role in STAFF_ROLES
        super().save(*args, **kwargs)

    @property
    def is_staff_role(self) -> bool:
        return self.role in STAFF_ROLES

    @property
    def is_portal_user(self) -> bool:
        return self.role in PORTAL_ROLES


class StaffInvite(models.Model):
    """A pending staff account — single-use token, expires, never carries a password."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    role = models.CharField(max_length=16, choices=Role.choices)
    token = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_staff_invite"

    def __str__(self) -> str:
        return f"invite {self.email} ({self.get_role_display()})"
