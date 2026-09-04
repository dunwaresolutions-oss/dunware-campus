"""Automatic write-auditing (signals) and read-auditing (DRF mixin)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.test import APIRequestFactory

from apps.audit import registry
from apps.audit.mixins import AuditReadMixin
from apps.audit.models import AuditAction, AuditEntry

pytestmark = pytest.mark.django_db


def test_unregistered_model_is_not_audited(make_user):
    make_user(username="nobody")
    assert not AuditEntry.objects.filter(
        object_type="accounts.User", action=AuditAction.CREATE
    ).exists()


def test_registered_model_gets_create_update_delete_entries():
    from apps.accounts.models import StaffInvite

    registry.register_audited(StaffInvite)
    try:
        invite = StaffInvite.objects.create(
            email="hooked@example.com",
            role="TEACHER",
            token="tok-hooked",
            expires_at=timezone.now() + timedelta(days=1),
        )
        oid = str(invite.pk)
        assert AuditEntry.objects.filter(
            action=AuditAction.CREATE, object_type="accounts.StaffInvite", object_id=oid
        ).exists()

        invite.accepted_at = timezone.now()
        invite.save(update_fields=["accepted_at"])
        updated = AuditEntry.objects.get(action=AuditAction.UPDATE, object_id=oid)
        assert updated.changed_fields == ["accepted_at"]

        invite.delete()
        assert AuditEntry.objects.filter(action=AuditAction.DELETE, object_id=oid).exists()
    finally:
        registry._AUDITED.discard(StaffInvite)


def test_audit_read_mixin_records_retrieve_and_list(make_user):
    from apps.accounts.models import User

    target = make_user(username="viewme")

    class _S(serializers.ModelSerializer):
        class Meta:
            model = User
            fields = ["id", "username"]

    class _V(AuditReadMixin, viewsets.ReadOnlyModelViewSet):
        queryset = User.objects.all().order_by("id")
        serializer_class = _S
        permission_classes = []
        authentication_classes = []
        audit_reads = True

    rf = APIRequestFactory()

    list_resp = _V.as_view({"get": "list"})(rf.get("/x/"))
    assert list_resp.status_code == 200
    assert AuditEntry.objects.filter(
        action=AuditAction.READ, summary__startswith="listed"
    ).exists()

    detail_resp = _V.as_view({"get": "retrieve"})(rf.get("/x/"), pk=str(target.pk))
    assert detail_resp.status_code == 200
    assert AuditEntry.objects.filter(
        action=AuditAction.READ, object_id=str(target.pk)
    ).exists()
