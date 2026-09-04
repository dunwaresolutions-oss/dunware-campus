from __future__ import annotations

import secrets

from rest_framework.permissions import SAFE_METHODS

from apps.accounts.models import Role
from apps.core.api import CampusViewSet
from apps.core.permissions import (
    AdminOnly,
    IsObjectOwnerOrStaff,
    MFAVerified,
    StaffOnly,
    StaffWriteAuthenticatedRead,
)

from .models import (
    AuthorizedPickup,
    Document,
    EmergencyContact,
    Group,
    GroupStaff,
    Guardian,
    GuardianLink,
    Observation,
    Student,
)
from .serializers import (
    AuthorizedPickupSerializer,
    DocumentSerializer,
    EmergencyContactSerializer,
    GroupSerializer,
    GroupStaffSerializer,
    GuardianLinkSerializer,
    GuardianSerializer,
    ObservationSerializer,
    StudentSerializer,
)

_ADMIN_ROLES = {Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK}
_INSTRUCTOR_ROLES = {Role.TEACHER, Role.TUTOR}


def _generate_student_number() -> str:
    for _ in range(10):
        candidate = f"S{secrets.randbelow(9_000_000) + 1_000_000}"
        if not Student.objects.filter(student_number=candidate).exists():
            return candidate
    raise RuntimeError("could not allocate a unique student number")  # pragma: no cover


class WriteAdminReadStaff(AdminOnly):
    """Any staff role may read; only admin-tier may write. Used for reference
    data (groups, staff assignments) that isn't person-level PII."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return StaffOnly().has_permission(request, view) and MFAVerified().has_permission(
                request, view
            )
        return super().has_permission(request, view) and MFAVerified().has_permission(
            request, view
        )


class GroupViewSet(CampusViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    permission_classes = [WriteAdminReadStaff]
    audit_reads = False


class GroupStaffViewSet(CampusViewSet):
    queryset = GroupStaff.objects.select_related("group", "user")
    serializer_class = GroupStaffSerializer
    permission_classes = [AdminOnly, MFAVerified]
    audit_reads = False


class StudentViewSet(CampusViewSet):
    serializer_class = StudentSerializer
    permission_classes = [StaffWriteAuthenticatedRead, MFAVerified, IsObjectOwnerOrStaff]

    def get_queryset(self):
        return Student.visible_queryset(self.request.user).select_related("primary_group")

    def perform_create(self, serializer):
        number = serializer.validated_data.get("student_number") or _generate_student_number()
        serializer.save(student_number=number)


class _StudentScopedViewSet(CampusViewSet):
    """Child records that live under a Student; scoped to the students the
    caller may see."""

    student_field = "student"

    def get_queryset(self):
        visible = Student.visible_queryset(self.request.user)
        return (
            self.model.objects.filter(**{f"{self.student_field}__in": visible})
            .order_by("-created_at")
        )


class GuardianViewSet(CampusViewSet):
    serializer_class = GuardianSerializer
    permission_classes = [StaffWriteAuthenticatedRead, MFAVerified, IsObjectOwnerOrStaff]

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, "role", None)
        qs = Guardian.objects.all()
        if role in _ADMIN_ROLES:
            return qs
        if role in _INSTRUCTOR_ROLES:
            visible = Student.visible_queryset(user)
            return qs.filter(links__student__in=visible).distinct()
        if role == Role.PARENT:
            return qs.filter(user=user)
        return qs.none()


class GuardianLinkViewSet(_StudentScopedViewSet):
    model = GuardianLink
    serializer_class = GuardianLinkSerializer


class EmergencyContactViewSet(_StudentScopedViewSet):
    model = EmergencyContact
    serializer_class = EmergencyContactSerializer


class AuthorizedPickupViewSet(_StudentScopedViewSet):
    model = AuthorizedPickup
    serializer_class = AuthorizedPickupSerializer


class ObservationViewSet(_StudentScopedViewSet):
    model = Observation
    serializer_class = ObservationSerializer

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class DocumentViewSet(_StudentScopedViewSet):
    model = Document
    serializer_class = DocumentSerializer

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)
