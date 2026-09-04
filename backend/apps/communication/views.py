from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.api import CampusViewSet
from apps.core.permissions import (
    AdminOnly,
    FrontOffice,
    IsObjectOwnerOrStaff,
    MFAVerified,
    StaffWriteAuthenticatedRead,
)
from apps.people.models import Guardian, Student

from .models import (
    Announcement,
    IncidentAcknowledgement,
    IncidentReport,
    Message,
    MessageThread,
    OutboundEmail,
)
from .serializers import (
    AnnouncementSerializer,
    IncidentAcknowledgementSerializer,
    IncidentReportSerializer,
    MessageSerializer,
    MessageThreadSerializer,
    OutboundEmailSerializer,
)
from .services import notify_incident, send_announcement

_ADMIN_ROLES = {Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK}
_INSTRUCTOR_ROLES = {Role.TEACHER, Role.TUTOR}


class AnnouncementPermission(BasePermission):
    """Any authenticated user reads (queryset-scoped); front office writes."""

    def has_permission(self, request, view):
        if not MFAVerified().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return FrontOffice().has_permission(request, view)


class AnnouncementViewSet(CampusViewSet):
    serializer_class = AnnouncementSerializer
    permission_classes = [AnnouncementPermission, IsObjectOwnerOrStaff]
    audit_reads = False

    def get_queryset(self):
        qs = Announcement.objects.alive().select_related("group", "author")
        role = getattr(self.request.user, "role", None)
        if role in _ADMIN_ROLES or role in _INSTRUCTOR_ROLES:
            return qs
        # parents: only published ones aimed at them
        visible_group_ids = list(
            Student.visible_queryset(self.request.user)
            .filter(enrolments__status="ACTIVE")
            .values_list("enrolments__group_id", flat=True)
        )
        return qs.filter(published_at__isnull=False).filter(
            Q(audience__in=[Announcement.Audience.ALL_PARENTS, Announcement.Audience.WHOLE_SITE])
            | Q(audience=Announcement.Audience.GROUP, group_id__in=visible_group_ids)
        )

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        ann = self.get_object()
        if ann.published_at is None:
            ann.published_at = timezone.now()
            ann.save(update_fields=["published_at"])
        send_announcement(ann, actor=request.user)
        return Response(self.get_serializer(ann).data)


class ThreadParticipant(BasePermission):
    def has_permission(self, request, view):
        return MFAVerified().has_permission(request, view) and bool(
            request.user and request.user.is_authenticated
        )


class MessageThreadViewSet(CampusViewSet):
    serializer_class = MessageThreadSerializer
    permission_classes = [ThreadParticipant, IsObjectOwnerOrStaff]
    audit_reads = True

    def get_queryset(self):
        user = self.request.user
        qs = MessageThread.objects.prefetch_related("messages", "participants")
        if getattr(user, "role", None) in (Role.SUPERADMIN, Role.ADMIN):
            return qs
        return qs.filter(participants=user).distinct()

    def perform_create(self, serializer):
        thread = serializer.save(created_by=self.request.user)
        thread.participants.add(self.request.user)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        thread = self.get_object()
        thread.closed = True
        thread.save(update_fields=["closed"])
        return Response(self.get_serializer(thread).data)


class MessageViewSet(CampusViewSet):
    serializer_class = MessageSerializer
    permission_classes = [ThreadParticipant]
    audit_reads = True

    def get_queryset(self):
        user = self.request.user
        qs = Message.objects.select_related("thread", "sender")
        if getattr(user, "role", None) in (Role.SUPERADMIN, Role.ADMIN):
            return qs
        return qs.filter(thread__participants=user).distinct()

    def perform_create(self, serializer):
        thread = serializer.validated_data["thread"]
        if not thread.is_visible_to(self.request.user):
            self.permission_denied(self.request, message="Not a participant.")
        msg = serializer.save(sender=self.request.user)
        MessageThread.objects.filter(pk=thread.pk).update(last_message_at=timezone.now())
        return msg


class IncidentReportViewSet(CampusViewSet):
    serializer_class = IncidentReportSerializer
    permission_classes = [StaffWriteAuthenticatedRead, MFAVerified, IsObjectOwnerOrStaff]
    audit_reads = True

    def get_queryset(self):
        qs = (
            IncidentReport.objects.alive()
            .select_related("student", "reported_by")
            .order_by("-occurred_at")
        )
        role = getattr(self.request.user, "role", None)
        if role in _ADMIN_ROLES:
            return qs
        visible = qs.filter(student__in=Student.visible_queryset(self.request.user))
        if role == Role.PARENT:
            return visible.exclude(status=IncidentReport.Status.DRAFT)
        return visible

    def perform_create(self, serializer):
        student = serializer.validated_data["student"]
        if not student.is_visible_to(self.request.user):
            self.permission_denied(self.request, message="Not your student.")
        serializer.save(reported_by=self.request.user)

    @action(detail=True, methods=["post"])
    def notify(self, request, pk=None):
        incident = self.get_object()
        log = notify_incident(incident, actor=request.user)
        return Response(
            {"status": incident.status, "recipients": len(log.to), "sent": bool(log.sent_at)},
            status=status.HTTP_200_OK,
        )


class IncidentAcknowledgementViewSet(CampusViewSet):
    """A guardian records that they have seen an incident report."""

    serializer_class = IncidentAcknowledgementSerializer
    permission_classes = [MFAVerified]
    audit_reads = True

    def get_queryset(self):
        qs = IncidentAcknowledgement.objects.select_related("incident", "guardian")
        role = getattr(self.request.user, "role", None)
        if role in _ADMIN_ROLES or role in _INSTRUCTOR_ROLES:
            return qs
        return qs.filter(incident__student__in=Student.visible_queryset(self.request.user))

    def perform_create(self, serializer):
        incident = serializer.validated_data["incident"]
        if getattr(self.request.user, "role", None) != Role.PARENT:
            self.permission_denied(self.request, message="Only a guardian acknowledges.")
        if not incident.is_visible_to(self.request.user):
            self.permission_denied(self.request, message="Not your child's incident.")
        guardian = Guardian.objects.filter(user=self.request.user).first()
        serializer.save(acknowledged_by=self.request.user, guardian=guardian)
        # all comms-guardians in? mark ACKNOWLEDGED
        expected = incident.student.guardian_links.filter(
            receives_communications=True
        ).values_list("guardian_id", flat=True)
        acked = incident.acknowledgements.values_list("guardian_id", flat=True)
        if expected and set(expected).issubset(set(acked)):
            incident.status = IncidentReport.Status.ACKNOWLEDGED
            incident.save(update_fields=["status"])


class OutboundEmailViewSet(CampusViewSet):
    queryset = OutboundEmail.objects.all()
    serializer_class = OutboundEmailSerializer
    permission_classes = [AdminOnly, MFAVerified]
    audit_reads = False
    http_method_names = ["get", "head", "options"]

    def get_object(self):
        return get_object_or_404(OutboundEmail, pk=self.kwargs["pk"])
