from __future__ import annotations

import datetime as dt

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.api import CampusViewSet
from apps.core.permissions import FrontOffice, MFAVerified, StaffOnly
from apps.people.models import GroupStaff

from .models import (
    AcademicYear,
    Closure,
    Room,
    SessionOccurrence,
    SessionTemplate,
    Term,
)
from .serializers import (
    AcademicYearSerializer,
    ClosureSerializer,
    RoomSerializer,
    RosterEntrySerializer,
    SessionOccurrenceSerializer,
    SessionTemplateSerializer,
    TermSerializer,
)
from .services import generate_occurrences

_ADMIN_ROLES = {Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK}
_INSTRUCTOR_ROLES = {Role.TEACHER, Role.TUTOR}


class StaffReadFrontOfficeWrite(BasePermission):
    """Reference / calendar data: any staff may read, front office writes."""

    def has_permission(self, request, view):
        if not MFAVerified().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return StaffOnly().has_permission(request, view)
        return FrontOffice().has_permission(request, view)


class _RefViewSet(CampusViewSet):
    permission_classes = [StaffReadFrontOfficeWrite]
    audit_reads = False


class RoomViewSet(_RefViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer


class AcademicYearViewSet(_RefViewSet):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer


class TermViewSet(_RefViewSet):
    queryset = Term.objects.select_related("academic_year")
    serializer_class = TermSerializer


class ClosureViewSet(_RefViewSet):
    queryset = Closure.objects.select_related("group")
    serializer_class = ClosureSerializer


def _instructor_group_ids(user):
    return GroupStaff.objects.filter(user=user, active=True).values_list("group_id", flat=True)


class SessionTemplateViewSet(_RefViewSet):
    serializer_class = SessionTemplateSerializer

    def get_queryset(self):
        qs = SessionTemplate.objects.select_related("group", "term", "room").order_by(
            "weekday", "start_time"
        )
        if getattr(self.request.user, "role", None) in _ADMIN_ROLES:
            return qs
        return qs.filter(group_id__in=_instructor_group_ids(self.request.user))

    @action(detail=True, methods=["post"])
    def generate(self, request, pk=None):
        template = self.get_object()
        from_date = request.data.get("from_date")
        to_date = request.data.get("to_date")
        result = generate_occurrences(
            template,
            from_date=dt.date.fromisoformat(from_date) if from_date else None,
            to_date=dt.date.fromisoformat(to_date) if to_date else None,
            actor=request.user,
        )
        return Response(result, status=status.HTTP_201_CREATED)


class SessionOccurrenceViewSet(CampusViewSet):
    serializer_class = SessionOccurrenceSerializer
    permission_classes = [StaffReadFrontOfficeWrite]
    audit_reads = False

    def get_queryset(self):
        qs = SessionOccurrence.objects.select_related("group", "room", "staff").order_by(
            "date", "start_time"
        )
        params = self.request.query_params
        if params.get("group"):
            qs = qs.filter(group_id=params["group"])
        if params.get("date"):
            qs = qs.filter(date=params["date"])
        if params.get("from"):
            qs = qs.filter(date__gte=params["from"])
        if params.get("to"):
            qs = qs.filter(date__lte=params["to"])
        if getattr(self.request.user, "role", None) in _ADMIN_ROLES:
            return qs
        return qs.filter(group_id__in=_instructor_group_ids(self.request.user))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        occ = self.get_object()
        occ.status = SessionOccurrence.Status.CANCELLED
        occ.cancelled_reason = request.data.get("reason", "")[:200]
        occ.save(update_fields=["status", "cancelled_reason"])
        return Response(self.get_serializer(occ).data)

    @action(detail=True, methods=["get"])
    def roster(self, request, pk=None):
        occ = self.get_object()
        rows = [
            {
                "student_id": e.student_id,
                "student_number": e.student.student_number,
                "display_name": e.student.display_name,
            }
            for e in occ.roster()
        ]
        return Response(RosterEntrySerializer(rows, many=True).data)
