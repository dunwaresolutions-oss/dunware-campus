"""
Auth events -> audit log.

``user_logged_in`` / ``user_logged_out`` / ``user_login_failed`` are Django's
own signals (django-axes also listens to the last one for lockout counting).
We record the fact; the PII filter keeps any credential material out of the
summary regardless.
"""
from __future__ import annotations

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from apps.audit.models import AuditAction
from apps.audit.services import record


@receiver(user_logged_in, dispatch_uid="accounts_logged_in")
def _on_logged_in(sender, request, user, **kwargs):
    record(AuditAction.LOGIN, user, summary=f"login: {user.username} ({user.role})", actor=user)


@receiver(user_logged_out, dispatch_uid="accounts_logged_out")
def _on_logged_out(sender, request, user, **kwargs):
    if user is not None:
        record(AuditAction.LOGOUT, user, summary=f"logout: {user.username}", actor=user)


@receiver(user_login_failed, dispatch_uid="accounts_login_failed")
def _on_login_failed(sender, credentials, request=None, **kwargs):
    username = (credentials or {}).get("username", "") or (credentials or {}).get("email", "")
    record(
        AuditAction.LOGIN_FAILED,
        summary=f"failed login for {username or 'unknown'}"[:255],
    )
