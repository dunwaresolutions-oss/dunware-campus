from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.api import CampusViewSet
from apps.core.permissions import FrontOffice, IsObjectOwnerOrStaff, MFAVerified, StaffOnly
from apps.people.models import GroupStaff, Student

from .models import (
    Assessment,
    AssessmentResult,
    AssessmentScheme,
    ReportCard,
    ReportCardEntry,
    RubricCriterion,
    RubricScore,
)
from .serializers import (
    AssessmentResultSerializer,
    AssessmentSchemeSerializer,
    AssessmentSerializer,
    ReportCardEntrySerializer,
    ReportCardSerializer,
    RubricCriterionSerializer,
    RubricScoreSerializer,
)
from .services import generate_report_card, release_report_card

_ADMIN_ROLES = {Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK}
_INSTRUCTOR_ROLES = {Role.TEACHER, Role.TUTOR}


def _instructor_group_ids(user):
    return GroupStaff.objects.filter(user=user, active=True).values_list("group_id", flat=True)


class _InstructorScopedViewSet(CampusViewSet):
    """Read scoping (via `scope()`/`group_path`) only narrows what already
    exists — it says nothing about a POST, which has no object yet. Every
    subclass below also implements `_group_for_create()` so `perform_create`
    can refuse to let an instructor write into a group they don't staff."""

    permission_classes = [StaffOnly, MFAVerified, IsObjectOwnerOrStaff]
    audit_reads = False
    group_path = "group_id"

    def _admin(self) -> bool:
        return getattr(self.request.user, "role", None) in _ADMIN_ROLES

    def scope(self, qs):
        if self._admin():
            return qs
        return qs.filter(**{f"{self.group_path}__in": _instructor_group_ids(self.request.user)})

    def _group_for_create(self, validated_data):
        """Return an object exposing the target group — either the Group
        itself, or a related object with a `.group_id` — for the payload
        about to be created. Subclasses override this per their FK shape."""
        return validated_data.get("group")

    def perform_create(self, serializer):
        if not self._admin():
            ref = self._group_for_create(serializer.validated_data)
            group_id = getattr(ref, "group_id", None) or getattr(ref, "pk", None)
            allowed = group_id and GroupStaff.objects.filter(
                user=self.request.user, active=True, group_id=group_id
            ).exists()
            if not allowed:
                self.permission_denied(self.request, message="Not your group.")
        serializer.save()


class AssessmentSchemeViewSet(_InstructorScopedViewSet):
    serializer_class = AssessmentSchemeSerializer

    def get_queryset(self):
        return self.scope(
            AssessmentScheme.objects.select_related("group", "term").prefetch_related("criteria")
        )


class RubricCriterionViewSet(_InstructorScopedViewSet):
    serializer_class = RubricCriterionSerializer
    group_path = "scheme__group_id"

    def get_queryset(self):
        return self.scope(RubricCriterion.objects.select_related("scheme"))

    def _group_for_create(self, validated_data):
        return validated_data.get("scheme")  # AssessmentScheme has .group_id


class AssessmentViewSet(_InstructorScopedViewSet):
    serializer_class = AssessmentSerializer

    def get_queryset(self):
        qs = Assessment.objects.select_related("scheme", "group").order_by("-date")
        if self._admin() or getattr(self.request.user, "role", None) in _INSTRUCTOR_ROLES:
            return self.scope(qs)
        # parents: released assessments for their child's groups
        gids = Student.visible_queryset(self.request.user).values_list(
            "enrolments__group_id", flat=True
        )
        return qs.filter(released=True, group_id__in=list(gids))

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [MFAVerified()]
        return super().get_permissions()

    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        a = self.get_object()
        a.released = True
        a.released_at = timezone.now()
        a.save(update_fields=["released", "released_at"])
        return Response(self.get_serializer(a).data)


class AssessmentResultViewSet(_InstructorScopedViewSet):
    serializer_class = AssessmentResultSerializer
    group_path = "assessment__group_id"

    def get_queryset(self):
        qs = AssessmentResult.objects.select_related("assessment", "student").order_by(
            "-created_at"
        )
        role = getattr(self.request.user, "role", None)
        if self._admin() or role in _INSTRUCTOR_ROLES:
            return self.scope(qs)
        return qs.filter(
            assessment__released=True,
            student__in=Student.visible_queryset(self.request.user),
        )

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [MFAVerified()]
        return super().get_permissions()

    def _group_for_create(self, validated_data):
        return validated_data.get("assessment")  # Assessment has .group_id

    def perform_create(self, serializer):
        if not self._admin():
            ref = self._group_for_create(serializer.validated_data)
            group_id = getattr(ref, "group_id", None)
            allowed = group_id and GroupStaff.objects.filter(
                user=self.request.user, active=True, group_id=group_id
            ).exists()
            if not allowed:
                self.permission_denied(self.request, message="Not your group.")
        serializer.save(graded_by=self.request.user)


class RubricScoreViewSet(_InstructorScopedViewSet):
    serializer_class = RubricScoreSerializer
    group_path = "result__assessment__group_id"

    def get_queryset(self):
        return self.scope(RubricScore.objects.select_related("result", "criterion"))

    def _group_for_create(self, validated_data):
        result = validated_data.get("result")
        return result.assessment if result else None


class ReportCardViewSet(CampusViewSet):
    serializer_class = ReportCardSerializer
    permission_classes = [MFAVerified, IsObjectOwnerOrStaff]
    audit_reads = True

    def get_queryset(self):
        qs = (
            ReportCard.objects.alive()
            .select_related("student", "term")
            .prefetch_related("entries")
        )
        role = getattr(self.request.user, "role", None)
        if role in _ADMIN_ROLES:
            return qs
        if role in _INSTRUCTOR_ROLES:
            return qs.filter(student__in=Student.visible_queryset(self.request.user))
        if role == Role.PARENT:
            return qs.filter(
                status=ReportCard.Status.RELEASED,
                student__in=Student.visible_queryset(self.request.user),
            )
        return qs.none()

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [MFAVerified()]
        return [FrontOffice(), MFAVerified()]

    @action(detail=True, methods=["post"])
    def generate(self, request, pk=None):
        card = self.get_object()
        result = generate_report_card(card, actor=request.user)
        return Response({**result, "status": card.status}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        card = self.get_object()
        release_report_card(card, actor=request.user)
        return Response(self.get_serializer(card).data)


class ReportCardEntryViewSet(_InstructorScopedViewSet):
    serializer_class = ReportCardEntrySerializer
    audit_reads = True

    def get_queryset(self):
        qs = ReportCardEntry.objects.select_related("report_card", "report_card__student")
        role = getattr(self.request.user, "role", None)
        if role in _ADMIN_ROLES:
            return qs
        return qs.filter(
            report_card__student__in=Student.visible_queryset(self.request.user)
        )

    def perform_create(self, serializer):
        if not self._admin():
            card = serializer.validated_data.get("report_card")
            if card is None or not card.student.is_visible_to(self.request.user):
                self.permission_denied(self.request, message="Not your student.")
        serializer.save()
