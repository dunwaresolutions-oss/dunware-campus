"""Deny-by-default permission building blocks."""
from __future__ import annotations

from apps.core.permissions import (
    AdminOnly,
    MFAVerified,
    RoleRequired,
    StaffAndMFAVerified,
    StaffOnly,
)


class _User:
    def __init__(self, *, authed=True, role="TEACHER", must_use_mfa=False, verified=False):
        self.is_authenticated = authed
        self.role = role
        self.must_use_mfa = must_use_mfa
        self._verified = verified

    def is_verified(self):
        return self._verified


class _Req:
    def __init__(self, user):
        self.user = user


def test_bare_role_required_denies_everyone():
    assert RoleRequired().has_permission(_Req(_User(role="ADMIN")), None) is False


def test_subclass_allows_only_listed_roles():
    assert StaffOnly().has_permission(_Req(_User(role="TEACHER")), None) is True
    assert StaffOnly().has_permission(_Req(_User(role="PARENT")), None) is False
    assert AdminOnly().has_permission(_Req(_User(role="TEACHER")), None) is False
    assert AdminOnly().has_permission(_Req(_User(role="ADMIN")), None) is True


def test_mfa_verified_lets_portal_users_through():
    assert MFAVerified().has_permission(_Req(_User(must_use_mfa=False)), None) is True


def test_mfa_verified_blocks_unverified_staff():
    unverified = _Req(_User(must_use_mfa=True, verified=False))
    verified = _Req(_User(must_use_mfa=True, verified=True))
    assert MFAVerified().has_permission(unverified, None) is False
    assert MFAVerified().has_permission(verified, None) is True


def test_anonymous_is_denied():
    assert MFAVerified().has_permission(_Req(_User(authed=False)), None) is False
    assert StaffOnly().has_permission(_Req(_User(authed=False)), None) is False


def test_staff_and_mfa_requires_both():
    assert StaffAndMFAVerified().has_permission(
        _Req(_User(role="TEACHER", must_use_mfa=True, verified=True)), None
    ) is True
    assert StaffAndMFAVerified().has_permission(
        _Req(_User(role="TEACHER", must_use_mfa=True, verified=False)), None
    ) is False
    assert StaffAndMFAVerified().has_permission(
        _Req(_User(role="PARENT", must_use_mfa=False, verified=False)), None
    ) is False
