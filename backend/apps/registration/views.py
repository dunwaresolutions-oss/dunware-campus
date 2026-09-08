from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.api import CampusViewSet
from apps.core.permissions import FrontOffice, MFAVerified, StaffOnly
from apps.people.models import Group, Student

from .models import Application, ApplicationDocument, Consent, Enrolment, Offer, WaitlistEntry
from .serializers import (
    ApplicationDocumentSerializer,
    ApplicationSerializer,
    ConsentSerializer,
    EnrolmentSerializer,
    OfferSerializer,
    WaitlistEntrySerializer,
)
from .services import convert_application, make_offer, respond_to_offer

_FRONT_OFFICE = {Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK}


class _FrontOfficeViewSet(CampusViewSet):
    permission_classes = [FrontOffice, MFAVerified]
    audit_reads = True


class ApplicationViewSet(_FrontOfficeViewSet):
    queryset = Application.objects.alive().select_related("desired_group", "student")
    serializer_class = ApplicationSerializer

    def perform_create(self, serializer):
        serializer.save(status=Application.Status.SUBMITTED)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        app = self.get_object()
        app.status = Application.Status.UNDER_REVIEW
        app.reviewed_by = request.user
        app.save(update_fields=["status", "reviewed_by", "updated_at"])
        return Response(self.get_serializer(app).data)

    @action(detail=True, methods=["post"])
    def make_offer(self, request, pk=None):
        app = self.get_object()
        group = get_object_or_404(Group, pk=request.data.get("group"))
        offer = make_offer(
            app, group=group, start_date=request.data["start_date"],
            expires_at=request.data["expires_at"], actor=request.user,
        )
        return Response(OfferSerializer(offer).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def waitlist(self, request, pk=None):
        app = self.get_object()
        group = get_object_or_404(Group, pk=request.data.get("group"))
        entry, _ = WaitlistEntry.objects.update_or_create(
            application=app,
            defaults={"group": group, "priority": int(request.data.get("priority", 100)),
                      "active": True},
        )
        app.status = Application.Status.WAITLISTED
        app.save(update_fields=["status", "updated_at"])
        return Response(WaitlistEntrySerializer(entry).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        app = self.get_object()
        app.status = Application.Status.DECLINED
        app.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(app).data)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        app = self.get_object()
        group = None
        if request.data.get("group"):
            group = get_object_or_404(Group, pk=request.data["group"])
        student, enrolment = convert_application(
            app, group=group, start_date=request.data.get("start_date"), actor=request.user
        )
        return Response(
            {"student": str(student.pk), "enrolment": str(enrolment.pk) if enrolment else None},
            status=status.HTTP_201_CREATED,
        )


class ApplicationDocumentViewSet(_FrontOfficeViewSet):
    queryset = ApplicationDocument.objects.select_related("application")
    serializer_class = ApplicationDocumentSerializer

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


class WaitlistEntryViewSet(_FrontOfficeViewSet):
    queryset = WaitlistEntry.objects.select_related("application", "group")
    serializer_class = WaitlistEntrySerializer
    audit_reads = False


class OfferViewSet(_FrontOfficeViewSet):
    queryset = Offer.objects.select_related("application", "group")
    serializer_class = OfferSerializer

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        offer = respond_to_offer(self.get_object(), accept=True, actor=request.user)
        return Response(self.get_serializer(offer).data)

    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        offer = respond_to_offer(self.get_object(), accept=False, actor=request.user)
        return Response(self.get_serializer(offer).data)


class _StaffReadFrontOfficeWrite(BasePermission):
    """Any staff role may read enrolments (scoped by the queryset); only the
    front office may change them."""

    def has_permission(self, request, view):
        if not MFAVerified().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return StaffOnly().has_permission(request, view)
        return FrontOffice().has_permission(request, view)


class EnrolmentViewSet(CampusViewSet):
    serializer_class = EnrolmentSerializer
    permission_classes = [_StaffReadFrontOfficeWrite]
    audit_reads = False

    def get_queryset(self):
        qs = Enrolment.objects.select_related("student", "group").order_by("-start_date")
        if getattr(self.request.user, "role", None) in _FRONT_OFFICE:
            return qs
        return qs.filter(student__in=Student.visible_queryset(self.request.user))

    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        enrolment = self.get_object()
        enrolment.end(on=request.data.get("end_date"))
        return Response(self.get_serializer(enrolment).data)


class _FrontOfficeOrParent(BasePermission):
    """Front office manages consents; a parent may read their own child's."""

    def has_permission(self, request, view):
        if not MFAVerified().has_permission(request, view):
            return False
        if FrontOffice().has_permission(request, view):
            return True
        return (
            request.method in SAFE_METHODS
            and getattr(request.user, "role", None) == Role.PARENT
        )


class ConsentViewSet(CampusViewSet):
    serializer_class = ConsentSerializer
    permission_classes = [_FrontOfficeOrParent]
    audit_reads = True

    def get_queryset(self):
        qs = Consent.objects.select_related("student", "granted_by").order_by("-recorded_at")
        role = getattr(self.request.user, "role", None)
        if role in _FRONT_OFFICE:
            pass
        elif role == Role.PARENT:
            qs = qs.filter(student__in=Student.visible_queryset(self.request.user))
        else:
            return qs.none()
        student = self.request.query_params.get("student")
        if student:
            qs = qs.filter(student_id=student)
        return qs

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)
