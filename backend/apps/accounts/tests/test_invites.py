"""Staff onboarding by single-use, time-boxed invitation."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import StaffInvite, User
from apps.accounts.services import create_staff_invite
from apps.audit.models import AuditAction, AuditEntry

pytestmark = pytest.mark.django_db

PW = "Sup3r-Secret-Pw!"
NEW_PW = "An0ther-Str0ng-Passphrase!"


def _login_verified(api, username, totp_for, user):
    _device, code = totp_for(user)
    return api.post(
        "/api/auth/login/",
        {"username": username, "password": PW, "otp": code()},
        format="json",
    )


def test_admin_issues_invite_and_invitee_sets_own_password(api, superadmin, totp_for):
    _login_verified(api, "root", totp_for, superadmin)
    issued = api.post(
        "/api/auth/invite/", {"email": "NewTeacher@Example.com", "role": "TEACHER"}, format="json"
    )
    assert issued.status_code == 201
    token = issued.data["token"]

    accepted = api.post(
        "/api/auth/invite/accept/",
        {"token": token, "username": "newteacher", "password": NEW_PW},
        format="json",
    )
    assert accepted.status_code == 201

    user = User.objects.get(username="newteacher")
    assert user.role == "TEACHER"
    assert user.email == "newteacher@example.com"
    assert user.must_use_mfa is True
    assert user.check_password(NEW_PW)
    assert AuditEntry.objects.filter(
        action=AuditAction.CREATE, object_type="accounts.User", object_id=str(user.pk)
    ).exists()


def test_non_admin_cannot_issue_an_invite(api, staff, totp_for):
    _login_verified(api, "teacher", totp_for, staff)
    r = api.post("/api/auth/invite/", {"email": "x@example.com", "role": "TEACHER"}, format="json")
    assert r.status_code == 403
    assert AuditEntry.objects.filter(action=AuditAction.PERMISSION_DENIED).exists()


def test_weak_password_is_rejected_on_accept(api):
    invite = create_staff_invite(email="a@example.com", role="TEACHER", invited_by=None)
    r = api.post(
        "/api/auth/invite/accept/",
        {"token": invite.token, "username": "weakling", "password": "password1234"},
        format="json",
    )
    assert r.status_code == 400
    assert not User.objects.filter(username="weakling").exists()


def test_expired_invite_is_rejected(api):
    invite = create_staff_invite(email="b@example.com", role="TEACHER", invited_by=None)
    StaffInvite.objects.filter(pk=invite.pk).update(
        expires_at=timezone.now() - timedelta(days=1)
    )
    r = api.post(
        "/api/auth/invite/accept/",
        {"token": invite.token, "username": "latecomer", "password": NEW_PW},
        format="json",
    )
    assert r.status_code == 400


def test_invite_is_single_use(api):
    invite = create_staff_invite(email="c@example.com", role="TEACHER", invited_by=None)
    first = api.post(
        "/api/auth/invite/accept/",
        {"token": invite.token, "username": "first", "password": NEW_PW},
        format="json",
    )
    assert first.status_code == 201
    second = api.post(
        "/api/auth/invite/accept/",
        {"token": invite.token, "username": "second", "password": NEW_PW},
        format="json",
    )
    assert second.status_code == 400
    assert not User.objects.filter(username="second").exists()
