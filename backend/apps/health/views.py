from __future__ import annotations

from apps.core.api import CampusViewSet
from apps.core.permissions import AdminOnly, MFAVerified
from apps.people.models import Student

from .models import (
    ActionPlan,
    Allergy,
    Condition,
    HealthAccessGrant,
    HealthProfile,
    Medication,
)
from .permissions import HealthDataPermission
from .serializers import (
    ActionPlanSerializer,
    AllergySerializer,
    ConditionSerializer,
    HealthAccessGrantSerializer,
    HealthProfileSerializer,
    MedicationSerializer,
)


class HealthAccessGrantViewSet(CampusViewSet):
    """Who may see health data — admin-tier only, and every change is audited."""

    queryset = HealthAccessGrant.objects.select_related("user", "granted_by")
    serializer_class = HealthAccessGrantSerializer
    permission_classes = [AdminOnly, MFAVerified]
    audit_reads = True

    def perform_create(self, serializer):
        serializer.save(granted_by=self.request.user)


class _HealthRecordViewSet(CampusViewSet):
    permission_classes = [HealthDataPermission]
    audit_reads = True
    student_field = "student"

    def get_queryset(self):
        visible = Student.visible_queryset(self.request.user)
        return (
            self.model.objects.filter(**{f"{self.student_field}__in": visible})
            .order_by("-created_at")
        )


class HealthProfileViewSet(_HealthRecordViewSet):
    model = HealthProfile
    serializer_class = HealthProfileSerializer


class AllergyViewSet(_HealthRecordViewSet):
    model = Allergy
    serializer_class = AllergySerializer


class ConditionViewSet(_HealthRecordViewSet):
    model = Condition
    serializer_class = ConditionSerializer


class MedicationViewSet(_HealthRecordViewSet):
    model = Medication
    serializer_class = MedicationSerializer


class ActionPlanViewSet(_HealthRecordViewSet):
    model = ActionPlan
    serializer_class = ActionPlanSerializer

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)
