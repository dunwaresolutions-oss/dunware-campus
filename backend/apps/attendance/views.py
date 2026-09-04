from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.api import CampusViewSet
from apps.core.permissions import IsObjectOwnerOrStaff, MFAVerified, StaffWriteAuthenticatedRead
from apps.people.models import Group, Student

from .models import AttendanceRecord
from .serializers import (
    AttendanceRecordSerializer,
    CheckInSerializer,
    CheckOutSerializer,
    MarkAbsentSerializer,
)
from .services import NotAuthorizedToCollect, check_in, check_out, mark_absent

_ADMIN_ROLES = {Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK}


class AttendanceRecordViewSet(CampusViewSet):
    serializer_class = AttendanceRecordSerializer
    permission_classes = [StaffWriteAuthenticatedRead, MFAVerified, IsObjectOwnerOrStaff]
    audit_reads = True

    def get_queryset(self):
        qs = AttendanceRecord.objects.select_related("student", "group").order_by("-date")
        params = self.request.query_params
        if params.get("group"):
            qs = qs.filter(group_id=params["group"])
        if params.get("date"):
            qs = qs.filter(date=params["date"])
        role = getattr(self.request.user, "role", None)
        if role in _ADMIN_ROLES:
            return qs
        return qs.filter(student__in=Student.visible_queryset(self.request.user))

    def _student_and_group(self, data):
        student = get_object_or_404(Student, pk=data["student"])
        group = get_object_or_404(Group, pk=data["group"])
        if not student.is_visible_to(self.request.user):
            self.permission_denied(self.request, message="Not your student.")
        return student, group

    @action(detail=False, methods=["post"], url_path="check-in")
    def check_in(self, request):
        s = CheckInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        student, group = self._student_and_group(s.validated_data)
        rec = check_in(
            student=student, group=group, date=s.validated_data.get("date"),
            by=request.user, dropped_off_by_name=s.validated_data["dropped_off_by_name"],
            late=s.validated_data["late"],
        )
        return Response(self.get_serializer(rec).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="check-out")
    def check_out(self, request, pk=None):
        rec = self.get_object()
        s = CheckOutSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            rec = check_out(
                record_obj=rec, by=request.user,
                pickup_id=s.validated_data.get("pickup_id"),
                guardian_link_id=s.validated_data.get("guardian_link_id"),
            )
        except NotAuthorizedToCollect as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response(self.get_serializer(rec).data)

    @action(detail=False, methods=["post"], url_path="mark-absent")
    def mark_absent(self, request):
        s = MarkAbsentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        student, group = self._student_and_group(s.validated_data)
        rec = mark_absent(
            student=student, group=group, date=s.validated_data.get("date"),
            by=request.user, excused=s.validated_data["excused"],
            note=s.validated_data["note"],
        )
        return Response(self.get_serializer(rec).data)
