from __future__ import annotations

import datetime as dt

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.api import CampusViewSet
from apps.core.permissions import FrontOffice, IsObjectOwnerOrStaff, MFAVerified, StaffOnly
from apps.people.models import Student

from .models import AvailabilityWindow, Booking, Offering, Slot
from .serializers import (
    AvailabilityWindowSerializer,
    BookingSerializer,
    OfferingSerializer,
    SlotSerializer,
)
from .services import BookingError, book, bookings_to_ics, cancel_booking, generate_slots

_ADMIN_ROLES = {Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK}
_INSTRUCTOR_ROLES = {Role.TEACHER, Role.TUTOR}


class CataloguePermission(BasePermission):
    """Offerings and slots: any authenticated user browses; front office (or the
    offering's own provider, checked per-object) manages."""

    def has_permission(self, request, view):
        if not MFAVerified().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return StaffOnly().has_permission(request, view)


class OfferingViewSet(CampusViewSet):
    queryset = Offering.objects.select_related("provider", "room")
    serializer_class = OfferingSerializer
    permission_classes = [CataloguePermission]
    audit_reads = False

    def _can_manage(self, offering=None) -> bool:
        role = getattr(self.request.user, "role", None)
        if role in _ADMIN_ROLES:
            return True
        return offering is not None and offering.provider_id == self.request.user.pk

    def perform_create(self, serializer):
        if getattr(self.request.user, "role", None) not in _ADMIN_ROLES:
            self.permission_denied(self.request, message="Only the office creates offerings.")
        serializer.save()

    def perform_update(self, serializer):
        if not self._can_manage(self.get_object()):
            self.permission_denied(self.request, message="Not your offering.")
        serializer.save()

    @action(detail=True, methods=["post"])
    def generate_slots(self, request, pk=None):
        offering = self.get_object()
        if not self._can_manage(offering):
            self.permission_denied(request, message="Not your offering.")
        result = generate_slots(
            offering,
            from_date=dt.date.fromisoformat(request.data["from_date"]),
            to_date=dt.date.fromisoformat(request.data["to_date"]),
            actor=request.user,
        )
        return Response(result, status=status.HTTP_201_CREATED)


class AvailabilityWindowViewSet(CampusViewSet):
    queryset = AvailabilityWindow.objects.select_related("offering")
    serializer_class = AvailabilityWindowSerializer
    permission_classes = [FrontOffice, MFAVerified]
    audit_reads = False


class SlotViewSet(CampusViewSet):
    serializer_class = SlotSerializer
    permission_classes = [CataloguePermission]
    audit_reads = False
    http_method_names = ["get", "head", "options", "post", "patch"]

    def get_queryset(self):
        qs = Slot.objects.select_related("offering").order_by("starts_at")
        params = self.request.query_params
        if params.get("offering"):
            qs = qs.filter(offering_id=params["offering"])
        if params.get("from"):
            qs = qs.filter(starts_at__gte=params["from"])
        if params.get("upcoming"):
            from django.utils import timezone

            qs = qs.filter(starts_at__gte=timezone.now())
        return qs

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        slot = self.get_object()
        role = getattr(request.user, "role", None)
        if role not in _ADMIN_ROLES and slot.offering.provider_id != request.user.pk:
            self.permission_denied(request, message="Not your slot.")
        slot.status = Slot.Status.CANCELLED
        slot.save(update_fields=["status"])
        slot.bookings.exclude(status=Booking.Status.CANCELLED).update(
            status=Booking.Status.CANCELLED, cancelled_at=request.data.get("_now") or None,
        )
        return Response(self.get_serializer(slot).data)


class BookingViewSet(CampusViewSet):
    serializer_class = BookingSerializer
    permission_classes = [MFAVerified, IsObjectOwnerOrStaff]
    audit_reads = True

    def get_queryset(self):
        qs = Booking.objects.select_related(
            "slot", "slot__offering", "student"
        ).order_by("-created_at")
        role = getattr(self.request.user, "role", None)
        if role in _ADMIN_ROLES:
            return qs
        if role in _INSTRUCTOR_ROLES:
            return qs.filter(slot__offering__provider=self.request.user) | qs.filter(
                student__in=Student.visible_queryset(self.request.user)
            )
        if role == Role.PARENT:
            return qs.filter(student__in=Student.visible_queryset(self.request.user))
        return qs.none()

    def create(self, request, *args, **kwargs):
        slot = get_object_or_404(Slot, pk=request.data.get("slot"))
        student = get_object_or_404(Student, pk=request.data.get("student"))
        role = getattr(request.user, "role", None)
        if role not in _ADMIN_ROLES and not student.is_visible_to(request.user):
            self.permission_denied(request, message="Not your student.")
        try:
            booking = book(slot=slot, student=student, by=request.user)
        except BookingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(booking).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        is_staff = getattr(request.user, "role", None) in (
            _ADMIN_ROLES | _INSTRUCTOR_ROLES
        )
        try:
            result = cancel_booking(
                booking=booking, by=request.user,
                note=request.data.get("note", ""),
                enforce_cutoff=not is_staff,
            )
        except BookingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        booking = result[0] if isinstance(result, tuple) else result
        promoted = result[1] if isinstance(result, tuple) else None
        data = self.get_serializer(booking).data
        data["promoted_booking"] = str(promoted.pk) if promoted else None
        return Response(data)

    @action(detail=False, methods=["get"], url_path="ics")
    def ics(self, request):
        mine = self.get_queryset().filter(
            status__in=[Booking.Status.CONFIRMED, Booking.Status.WAITLISTED]
        )
        body = bookings_to_ics(mine)
        resp = HttpResponse(body, content_type="text/calendar; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="campus-bookings.ics"'
        return resp
