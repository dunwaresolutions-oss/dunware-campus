"""The read-only /api/audit/ surface — admin tier only.

Note: logging in through `auth_client` itself writes LOGIN / MFA_VERIFIED
rows, so these assert on *known* entries rather than absolute counts.
"""
from __future__ import annotations

import pytest

from apps.audit.models import AuditAction, AuditEntry

pytestmark = pytest.mark.django_db


@pytest.fixture
def some_entries(db):
    AuditEntry.objects.create(action=AuditAction.LOGIN_FAILED, actor_label="ghost",
                              summary="bad password here")
    AuditEntry.objects.create(action=AuditAction.LOCKOUT, actor_label="ghost",
                              summary="locked out here")
    AuditEntry.objects.create(action=AuditAction.READ, actor_label="director",
                              object_type="health.Allergy", object_id="abc",
                              summary="viewed allergy here")
    AuditEntry.objects.create(action=AuditAction.EXPORT, actor_label="director",
                              object_type="people.Student", summary="data export here")


def _summaries(resp):
    return {e["summary"] for e in resp.data["results"]}


def test_superadmin_sees_every_kind(auth_client, superadmin, some_entries):
    r = auth_client(superadmin).get("/api/audit/")
    assert r.status_code == 200
    assert {"bad password here", "locked out here", "viewed allergy here",
            "data export here"} <= _summaries(r)


def test_admin_can_list(auth_client, admin_user, some_entries):
    assert auth_client(admin_user).get("/api/audit/").status_code == 200


def test_front_desk_teacher_are_denied(auth_client, front_desk, staff, some_entries):
    assert auth_client(front_desk).get("/api/audit/").status_code == 403
    assert auth_client(staff).get("/api/audit/").status_code == 403


def test_parent_is_denied(auth_client, parent, some_entries):
    assert auth_client(parent).get("/api/audit/").status_code == 403


def test_preset_and_action_filters(auth_client, superadmin, some_entries):
    c = auth_client(superadmin)
    sec = _summaries(c.get("/api/audit/?set=security"))
    assert {"bad password here", "locked out here"} <= sec
    assert "viewed allergy here" not in sec

    reads = _summaries(c.get("/api/audit/?action=READ"))
    assert reads == {"viewed allergy here"}

    both = _summaries(c.get("/api/audit/?action=EXPORT,LOCKOUT"))
    assert both == {"data export here", "locked out here"}

    assert _summaries(c.get("/api/audit/?q=allergy")) == {"viewed allergy here"}


def test_summary_counts_last_24h(auth_client, superadmin, some_entries):
    r = auth_client(superadmin).get("/api/audit/summary/")
    assert r.status_code == 200
    assert r.data["login_failed"] >= 1
    assert r.data["lockout"] >= 1
    assert r.data["governance"] == 1   # exactly the one EXPORT row
    assert r.data["total"] >= 4


def test_reading_the_log_does_not_write_to_it(auth_client, superadmin, some_entries):
    c = auth_client(superadmin)
    c.get("/api/audit/")
    n1 = AuditEntry.objects.count()
    c.get("/api/audit/")
    c.get("/api/audit/summary/")
    assert AuditEntry.objects.count() == n1
