"""Shared pytest fixtures for the Campus backend."""
from __future__ import annotations

import pytest
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.test import APIClient

from apps.accounts.models import Role, User


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def make_user(db):
    def _make(username="user", password="Sup3r-Secret-Pw!", role=Role.FRONT_DESK, **extra):
        user = User(username=username, role=role, **extra)
        user.set_password(password)
        user.save()
        return user

    return _make


@pytest.fixture
def parent(make_user):
    return make_user(username="parent", role=Role.PARENT)


@pytest.fixture
def staff(make_user):
    return make_user(username="teacher", role=Role.TEACHER)


@pytest.fixture
def superadmin(make_user):
    return make_user(username="root", role=Role.SUPERADMIN)


@pytest.fixture
def totp_for():
    """Return (device, code_factory) for a confirmed TOTP device on `user`."""
    from django_otp.oath import totp as _totp

    def _make(user, confirmed=True):
        device = TOTPDevice.objects.create(user=user, name="default", confirmed=confirmed)

        def code() -> str:
            value = _totp(
                device.bin_key, step=device.step, t0=device.t0, digits=device.digits, drift=0
            )
            return str(value).zfill(device.digits)

        return device, code

    return _make
