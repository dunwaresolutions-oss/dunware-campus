"""The `create_admin` management command - first-run superadmin bootstrap."""
from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db

STRONG = "Str0ng-Local-Passphrase!"


def test_creates_a_superadmin():
    call_command(
        "create_admin",
        username="founder",
        email="founder@example.test",
        password=STRONG,
    )
    u = User.objects.get(username="founder")
    assert u.is_superuser and u.role == Role.SUPERADMIN and u.is_active
    assert u.check_password(STRONG)


def test_refuses_a_second_superadmin():
    call_command("create_admin", username="a", email="a@example.test", password=STRONG)
    with pytest.raises(CommandError, match="already exists"):
        call_command(
            "create_admin", username="b", email="b@example.test", password=STRONG
        )
    assert User.objects.filter(is_superuser=True).count() == 1


def test_rejects_a_weak_password():
    with pytest.raises(CommandError, match="at least 12 characters"):
        call_command(
            "create_admin", username="x", email="x@example.test", password="short"
        )
    assert not User.objects.filter(is_superuser=True).exists()


def test_reads_password_from_the_environment(monkeypatch):
    monkeypatch.setenv("CAMPUS_ADMIN_PASSWORD", STRONG)
    call_command("create_admin", username="envuser", email="env@example.test")
    assert User.objects.get(username="envuser").check_password(STRONG)
