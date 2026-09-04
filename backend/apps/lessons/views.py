from __future__ import annotations

from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.api import CampusViewSet
from apps.core.permissions import IsObjectOwnerOrStaff, MFAVerified, StaffOnly
from apps.people.models import GroupStaff

from .models import CurriculumUnit, LessonPlan, LessonResource
from .serializers import (
    CurriculumUnitSerializer,
    LessonPlanSerializer,
    LessonResourceSerializer,
)

_ADMIN_ROLES = {Role.SUPERADMIN, Role.ADMIN}


def _instructor_group_ids(user):
    return GroupStaff.objects.filter(user=user, active=True).values_list("group_id", flat=True)


class _LessonsViewSet(CampusViewSet):
    permission_classes = [StaffOnly, MFAVerified, IsObjectOwnerOrStaff]
    audit_reads = False


class CurriculumUnitViewSet(_LessonsViewSet):
    serializer_class = CurriculumUnitSerializer

    def get_queryset(self):
        qs = CurriculumUnit.objects.select_related("group", "term").order_by("group", "sequence")
        if getattr(self.request.user, "role", None) in _ADMIN_ROLES:
            return qs
        return qs.filter(group_id__in=_instructor_group_ids(self.request.user))


class LessonPlanViewSet(_LessonsViewSet):
    serializer_class = LessonPlanSerializer

    def get_queryset(self):
        qs = LessonPlan.objects.alive().select_related("group", "unit", "author").order_by("-date")
        params = self.request.query_params
        if params.get("group"):
            qs = qs.filter(group_id=params["group"])
        if getattr(self.request.user, "role", None) in _ADMIN_ROLES:
            return qs
        return qs.filter(group_id__in=_instructor_group_ids(self.request.user))

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        plan = self.get_object()
        plan.status = LessonPlan.Status.PUBLISHED
        plan.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(plan).data)


class LessonResourceViewSet(_LessonsViewSet):
    serializer_class = LessonResourceSerializer

    def get_queryset(self):
        qs = LessonResource.objects.select_related("lesson", "lesson__group")
        if getattr(self.request.user, "role", None) in _ADMIN_ROLES:
            return qs
        return qs.filter(lesson__group_id__in=_instructor_group_ids(self.request.user))
