"""
Shared DRF base for every Campus feature viewset.

Defaults that a PII system should never have to remember to switch on:
staff role + MFA-verified session, object-level visibility via
``obj.is_visible_to(user)``, and automatic READ auditing. A subclass narrows
further (health data, admin-only) and supplies ``get_queryset`` scoped to what
the caller may see.
"""
from __future__ import annotations

from rest_framework import viewsets

from apps.audit.mixins import AuditReadMixin
from apps.core.permissions import IsObjectOwnerOrStaff, MFAVerified, StaffOnly


class CampusViewSet(AuditReadMixin, viewsets.ModelViewSet):
    permission_classes = [StaffOnly, MFAVerified, IsObjectOwnerOrStaff]
    audit_reads = True

    def perform_create(self, serializer):
        serializer.save()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx
