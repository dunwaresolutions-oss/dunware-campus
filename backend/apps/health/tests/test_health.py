from __future__ import annotations

import pytest
from django.db import connection

from apps.accounts.models import Role
from apps.audit.models import AuditAction, AuditEntry
from apps.health.models import Allergy, Condition, HealthAccessGrant
from apps.people.tests.factories import enrol, make_group, make_student

pytestmark = pytest.mark.django_db


def test_health_fields_are_encrypted_at_rest():
    s = make_student()
    a = Allergy.objects.create(student=s, allergen="peanut", reaction="anaphylaxis",
                               severity=Allergy.Severity.ANAPHYLAXIS)
    a.refresh_from_db()
    assert a.allergen == "peanut"
    with connection.cursor() as cur:
        cur.execute("SELECT allergen FROM health_allergy")
        (raw,) = cur.fetchone()
    assert raw.startswith("cg1:") and "peanut" not in raw


def test_user_may_view_health_requires_admin_or_grant(make_user):
    admin = make_user(username="a", role=Role.ADMIN)
    teacher = make_user(username="t", role=Role.TEACHER)
    assert HealthAccessGrant.user_may_view_health(admin) is True
    assert HealthAccessGrant.user_may_view_health(teacher) is False
    HealthAccessGrant.objects.create(user=teacher, active=True)
    assert HealthAccessGrant.user_may_view_health(teacher) is True


def test_health_api_blocked_without_grant(auth_client, staff):
    s = make_student()
    Condition.objects.create(student=s, name="asthma")
    client = auth_client(staff)
    assert client.get("/api/health/conditions/").status_code == 403


def test_health_api_allowed_with_grant_and_audited(auth_client, staff):
    group = make_group()
    s = make_student()
    enrol(s, group)
    from apps.people.tests.factories import assign_staff
    assign_staff(group, staff)
    Condition.objects.create(student=s, name="asthma")
    HealthAccessGrant.objects.create(user=staff, active=True)

    client = auth_client(staff)
    resp = client.get("/api/health/conditions/")
    assert resp.status_code == 200
    assert len(resp.data["results"]) == 1
    assert resp.data["results"][0]["name"] == "asthma"
    assert AuditEntry.objects.filter(
        action=AuditAction.READ, summary__icontains="condition"
    ).exists()


def test_admin_can_grant_health_access(auth_client, admin_user, make_user):
    teacher = make_user(username="newnurse", role=Role.TEACHER)
    client = auth_client(admin_user)
    resp = client.post("/api/health/access-grants/",
                       {"user": str(teacher.pk), "reason": "school nurse"}, format="json")
    assert resp.status_code == 201
    assert HealthAccessGrant.user_may_view_health(teacher) is True
