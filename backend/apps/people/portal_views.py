"""
The restricted parent / student portal surface (see docs/DATA_MODEL.md).

Everything here is read-scoped by the same `Student.visible_queryset` /
`is_visible_to` the staff API uses. The only writes a portal user gets are:
a **contact-change request** (staff approve/reject — no direct edit), and
recording a **consent** decision (a new versioned row, never an update).
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.audit.mixins import AuditReadMixin
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.core.permissions import FrontOffice, MFAVerified, PortalUser
from apps.registration.models import Consent

from .models import ContactChangeRequest, Guardian, Student
from .portal_serializers import (
    ContactChangeRequestSerializer,
    ContactChangeSubmitSerializer,
    PortalConsentSerializer,
)
from .portal_services import build_dashboard, review_contact_change, submit_contact_change

_FRONT_OFFICE = {Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK}


class PortalDashboardView(APIView):
    permission_classes = [IsAuthenticated, PortalUser]

    def get(self, request):
        record(AuditAction.READ, summary="portal dashboard viewed", actor=request.user)
        return Response(build_dashboard(request.user))


class ContactChangeRequestViewSet(AuditReadMixin, viewsets.ModelViewSet):
    serializer_class = ContactChangeRequestSerializer
    audit_reads = True
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated(), MFAVerified()]
        if self.action in ("approve", "reject"):
            return [FrontOffice(), MFAVerified()]
        return [IsAuthenticated(), PortalUser()]

    def get_queryset(self):
        qs = ContactChangeRequest.objects.select_related(
            "guardian", "requested_by", "reviewed_by"
        )
        if getattr(self.request.user, "role", None) in _FRONT_OFFICE:
            status_q = self.request.query_params.get("status")
            return qs.filter(status=status_q) if status_q else qs
        return qs.filter(requested_by=self.request.user)

    def create(self, request, *args, **kwargs):
        s = ContactChangeSubmitSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        guardian = Guardian.objects.filter(user=request.user).first()
        if guardian is None:
            raise PermissionDenied("Your account is not linked to a guardian record.")
        student = None
        if s.validated_data.get("student"):
            student = get_object_or_404(Student, pk=s.validated_data["student"])
        req = submit_contact_change(
            user=request.user, guardian=guardian,
            field=s.validated_data["field"],
            proposed_value=s.validated_data["proposed_value"],
            reason=s.validated_data["reason"], student=student,
        )
        return Response(self.get_serializer(req).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        req = review_contact_change(
            req=self.get_object(), approve=True, by=request.user,
            note=request.data.get("note", ""),
        )
        return Response(self.get_serializer(req).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        req = review_contact_change(
            req=self.get_object(), approve=False, by=request.user,
            note=request.data.get("note", ""),
        )
        return Response(self.get_serializer(req).data)


class PortalConsentView(APIView):
    """A guardian records a consent decision — always a new versioned row."""

    permission_classes = [IsAuthenticated, PortalUser]

    def post(self, request):
        s = PortalConsentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        student = get_object_or_404(Student, pk=s.validated_data["student"])
        if not student.is_visible_to(request.user):
            raise PermissionDenied("Not your child.")
        kind = s.validated_data["kind"]
        if kind not in Consent.Kind.values:
            raise PermissionDenied(f"Unknown consent kind '{kind}'.")
        guardian = Guardian.objects.filter(user=request.user).first()
        consent = Consent.objects.create(
            student=student, kind=kind, granted=s.validated_data["granted"],
            version=s.validated_data["version"], granted_by=guardian,
            granted_by_name=str(guardian) if guardian else request.user.get_full_name(),
            recorded_by=request.user, notes=s.validated_data["note"],
        )
        record(AuditAction.CREATE, consent, summary="consent recorded via portal",
               actor=request.user)
        return Response(
            {"id": str(consent.pk), "kind": consent.kind, "granted": consent.granted,
             "version": consent.version},
            status=status.HTTP_201_CREATED,
        )
