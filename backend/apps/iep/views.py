from __future__ import annotations

from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.api import CampusViewSet
from apps.core.text_search import multi_word_icontains
from apps.people.models import Student

from .models import IEP, IEPAccommodation, IEPGoal, IEPReview, IEPService
from .serializers import (
    IEPAccommodationSerializer,
    IEPGoalSerializer,
    IEPReviewSerializer,
    IEPSerializer,
    IEPServiceSerializer,
)
from .services import render_iep_html

_ADMIN_ROLES = {Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK}


class IEPViewSet(CampusViewSet):
    serializer_class = IEPSerializer
    audit_reads = True

    def get_queryset(self):
        visible = Student.visible_queryset(self.request.user)
        qs = (
            IEP.objects.alive()
            .filter(student__in=visible)
            .select_related("student", "case_manager")
            .prefetch_related("iepgoals", "iepaccommodations", "iepservices", "iepreviews")
        )
        params = self.request.query_params
        if params.get("student"):
            qs = qs.filter(student_id=params["student"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        q = (params.get("q") or "").strip()
        if q:
            qs = qs.filter(multi_word_icontains(q, [
                "student__first_name", "student__last_name",
                "student__preferred_name", "primary_concern",
            ]))
        return qs

    def perform_create(self, serializer):
        student = serializer.validated_data["student"]
        if not student.is_visible_to(self.request.user):
            self.permission_denied(self.request, message="Not your student.")
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["get"])
    def document(self, request, pk=None):
        """Rendered, self-contained IEP HTML (school letterhead + full plan)."""
        return Response({"html": render_iep_html(self.get_object())})


class _IEPChildViewSet(CampusViewSet):
    audit_reads = True

    def get_queryset(self):
        visible = Student.visible_queryset(self.request.user)
        qs = self.model.objects.filter(iep__student__in=visible).filter(
            iep__deleted_at__isnull=True
        )
        if self.request.query_params.get("iep"):
            qs = qs.filter(iep_id=self.request.query_params["iep"])
        return qs

    def perform_create(self, serializer):
        iep = serializer.validated_data["iep"]
        if not iep.is_visible_to(self.request.user):
            self.permission_denied(self.request, message="Not your student's IEP.")
        serializer.save()


class IEPGoalViewSet(_IEPChildViewSet):
    model = IEPGoal
    serializer_class = IEPGoalSerializer


class IEPAccommodationViewSet(_IEPChildViewSet):
    model = IEPAccommodation
    serializer_class = IEPAccommodationSerializer


class IEPServiceViewSet(_IEPChildViewSet):
    model = IEPService
    serializer_class = IEPServiceSerializer


class IEPReviewViewSet(_IEPChildViewSet):
    model = IEPReview
    serializer_class = IEPReviewSerializer

    def perform_create(self, serializer):
        iep = serializer.validated_data["iep"]
        if not iep.is_visible_to(self.request.user):
            self.permission_denied(self.request, message="Not your student's IEP.")
        serializer.save(recorded_by=self.request.user)
