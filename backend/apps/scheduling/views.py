from __future__ import annotations

import datetime as dt

from django.db import models
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
    EarlyDismissal,
    Room,
    SessionOccurrence,
    SessionTemplate,
    Term,
)
from .serializers import (
    AcademicYearSerializer,
    ClosureSerializer,
    EarlyDismissalSerializer,
    RoomSerializer,
    RosterEntrySerializer,
    SessionOccurrenceSerializer,
    SessionTemplateSerializer,
    TermSerializer,
)
from .services import generate_occurrences

_ADMIN_ROLES = {Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK}
_INSTRUCTOR_ROLES = {Role.TEACHER, Role.TUTOR}


def _student_group_ids(student_id):
    """Every group a student is actively enrolled in — homeroom AND every
    course-of-study section, so "show her schedule" means her whole
    timetable, not just the one primary_group."""
    from apps.registration.models import Enrolment

    return Enrolment.objects.filter(
        student_id=student_id, status=Enrolment.Status.ACTIVE
    ).values_list("group_id", flat=True)


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


class EarlyDismissalViewSet(_RefViewSet):
    queryset = EarlyDismissal.objects.select_related("group")
    serializer_class = EarlyDismissalSerializer

    @action(detail=True, methods=["post"])
    def notify(self, request, pk=None):
        from apps.communication.services import notify_early_dismissal

        dismissal = self.get_object()
        log = notify_early_dismissal(dismissal, actor=request.user)
        return Response(
            {"sent": bool(log.sent_at), "recipients": len(log.to)},
            status=status.HTTP_200_OK,
        )


def _instructor_group_ids(user):
    return GroupStaff.objects.filter(user=user, active=True).values_list("group_id", flat=True)


def _parse_calendar_range(request):
    """Shared by the staff and portal calendar endpoints: parse+clamp
    ``from``/``to``, returning ``(start, end, None)`` or ``(None, None,
    error_response)``."""
    try:
        start = dt.date.fromisoformat(request.query_params["from"])
        end = dt.date.fromisoformat(request.query_params["to"])
    except (KeyError, ValueError):
        return None, None, Response(
            {"detail": "from and to (YYYY-MM-DD) are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if end < start:
        start, end = end, start
    if (end - start).days > 62:
        end = start + dt.timedelta(days=62)
    return start, end, None


def calendar_payload(
    start: dt.date, end: dt.date, *,
    group_id=None, student_id=None, scope_group_ids=None,
) -> dict:
    """Sessions + closures + early dismissals in ``[start, end]``, shaped for
    the calendar views. ``scope_group_ids``, when given, additionally
    restricts everything to that set of groups (instructor scoping on the
    staff side; the portal instead scopes by resolving ``student_id`` to a
    single guardian-verified student before ever calling this)."""
    qs = SessionOccurrence.objects.select_related("group", "room", "staff").filter(
        date__gte=start, date__lte=end
    )
    if group_id:
        qs = qs.filter(group_id=group_id)
    if student_id:
        qs = qs.filter(group_id__in=_student_group_ids(student_id))
    if scope_group_ids is not None:
        qs = qs.filter(group_id__in=scope_group_ids)

    closures = Closure.objects.select_related("group").filter(
        start_date__lte=end, end_date__gte=start
    )
    if scope_group_ids is not None:
        closures = closures.filter(
            models.Q(group__isnull=True) | models.Q(group_id__in=scope_group_ids)
        )

    dismissals = EarlyDismissal.objects.select_related("group").filter(
        date__gte=start, date__lte=end
    )
    if scope_group_ids is not None:
        dismissals = dismissals.filter(
            models.Q(group__isnull=True) | models.Q(group_id__in=scope_group_ids)
        )
    dismissals = list(dismissals)
    by_date: dict[dt.date, list[EarlyDismissal]] = {}
    for ed in dismissals:
        by_date.setdefault(ed.date, []).append(ed)

    occurrences = list(qs.order_by("date", "start_time"))
    sessions_data = SessionOccurrenceSerializer(occurrences, many=True).data
    for row, occ in zip(sessions_data, occurrences, strict=True):
        match = next(
            (ed for ed in by_date.get(occ.date, ()) if ed.applies_to(occ.date, occ.group_id)),
            None,
        )
        row["early_dismissal_time"] = match.dismissal_time.strftime("%H:%M") if match else None

    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "sessions": sessions_data,
        "closures": [
            {
                "id": str(c.id),
                "start_date": c.start_date.isoformat(),
                "end_date": c.end_date.isoformat(),
                "reason": c.reason,
                "group": c.group_id,
                "group_name": c.group.name if c.group_id else None,
            }
            for c in closures
        ],
        "early_dismissals": [
            {
                "id": str(ed.id),
                "date": ed.date.isoformat(),
                "dismissal_time": ed.dismissal_time.strftime("%H:%M"),
                "reason": ed.reason,
                "group": ed.group_id,
                "group_name": ed.group.name if ed.group_id else None,
            }
            for ed in dismissals
        ],
    }


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
        if params.get("student"):
            qs = qs.filter(group_id__in=_student_group_ids(params["student"]))
        if params.get("date"):
            qs = qs.filter(date=params["date"])
        if params.get("from"):
            qs = qs.filter(date__gte=params["from"])
        if params.get("to"):
            qs = qs.filter(date__lte=params["to"])
        if getattr(self.request.user, "role", None) in _ADMIN_ROLES:
            return qs
        return qs.filter(group_id__in=_instructor_group_ids(self.request.user))

    @action(detail=False, methods=["get"])
    def calendar(self, request):
        """``GET /api/sessions/calendar/?from=YYYY-MM-DD&to=YYYY-MM-DD[&group=ID]``

        A flat, un-paginated payload for the calendar views: the sessions in
        the range (role-scoped exactly like the list) plus the closures that
        overlap it, so the grid can shade non-teaching days. The span is
        capped at 62 days.
        """
        start, end, err = _parse_calendar_range(request)
        if err:
            return err

        role = getattr(request.user, "role", None)
        scope_group_ids = None if role in _ADMIN_ROLES else list(_instructor_group_ids(request.user))

        payload = calendar_payload(
            start, end,
            group_id=request.query_params.get("group"),
            student_id=request.query_params.get("student"),
            scope_group_ids=scope_group_ids,
        )
        return Response(payload)

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
