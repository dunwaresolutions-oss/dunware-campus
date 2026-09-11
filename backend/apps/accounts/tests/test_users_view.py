from __future__ import annotations

import pytest

from apps.accounts.models import Role

pytestmark = pytest.mark.django_db


def test_any_staff_role_can_list_the_staff_directory(auth_client, make_user):
    front_desk = make_user(username="fd", role=Role.FRONT_DESK)
    make_user(username="t1", role=Role.TEACHER)
    resp = auth_client(front_desk).get("/api/auth/users/")
    assert resp.status_code == 200
    usernames = {u["username"] for u in resp.data}
    assert {"fd", "t1"}.issubset(usernames)


def test_parents_and_students_are_never_listed(auth_client, make_user, admin_user):
    make_user(username="mom", role=Role.PARENT)
    make_user(username="kid-login", role=Role.STUDENT)
    resp = auth_client(admin_user).get("/api/auth/users/")
    roles = {u["role"] for u in resp.data}
    assert "PARENT" not in roles
    assert "STUDENT" not in roles


def test_a_parent_cannot_reach_the_staff_directory(auth_client, parent):
    resp = auth_client(parent).get("/api/auth/users/")
    assert resp.status_code == 403
