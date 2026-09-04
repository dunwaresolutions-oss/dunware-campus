"""
Staff onboarding by invitation.

Admins never type a colleague's password. They create a ``StaffInvite`` (role +
email, single-use token, time-boxed); the invitee follows the link and sets
their own password, which lands Argon2-hashed. Every step is audited.
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.models import AuditAction
from apps.audit.services import record

from .models import STAFF_ROLES, Role, StaffInvite, User

INVITE_TTL = timedelta(days=7)


def _invite_error(message: str) -> ValidationError:
    """A field-scoped error on the invitation token."""
    return ValidationError({"token": message})


def create_staff_invite(*, email: str, role: str, invited_by: User | None) -> StaffInvite:
    if role not in {r.value for r in STAFF_ROLES}:
        raise ValidationError({"role": "Not a staff role."})
    invite = StaffInvite.objects.create(
        email=email.strip().lower(),
        role=role,
        token=secrets.token_urlsafe(32),
        invited_by=invited_by,
        expires_at=timezone.now() + INVITE_TTL,
    )
    record(
        AuditAction.CREATE,
        invite,
        summary=f"staff invite issued: {invite.email} as {role}",
    )
    return invite


@transaction.atomic
def accept_staff_invite(*, token: str, username: str, password: str) -> User:
    try:
        invite = StaffInvite.objects.select_for_update().get(token=token)
    except StaffInvite.DoesNotExist:
        raise _invite_error("Unknown or already-used invitation.") from None

    if invite.accepted_at is not None:
        raise _invite_error("This invitation has already been used.")
    if invite.expires_at < timezone.now():
        raise _invite_error("This invitation has expired.")

    username = username.strip()
    if User.objects.filter(username__iexact=username).exists():
        raise ValidationError({"username": "That username is taken."})

    user = User(username=username, email=invite.email, role=invite.role, is_active=True)
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise ValidationError({"password": list(exc.messages)}) from exc
    user.set_password(password)
    user.last_password_change = timezone.now()
    user.save()

    invite.accepted_at = timezone.now()
    invite.save(update_fields=["accepted_at"])

    record(AuditAction.CREATE, user, summary=f"staff account created via invite ({user.role})")
    return user


def bootstrap_superadmin(*, username: str, email: str, password: str) -> User:
    """First-run only: the installer calls this once to create the initial
    SUPERADMIN. Refuses to run if any superuser already exists."""
    if User.objects.filter(is_superuser=True).exists():
        raise ValidationError("A superadmin already exists.")
    user = User(username=username, email=email, role=Role.SUPERADMIN, is_active=True)
    user.set_password(password)
    user.last_password_change = timezone.now()
    user.save()
    record(AuditAction.CREATE, user, summary="initial superadmin bootstrapped")
    return user
