"""
Staff intranet chat. Poller-only by design — the same trade-off already made
for billing (no webhooks) and made here to avoid adding an ASGI/Redis stack to
a WSGI + waitress, no-external-dependency deployment. The frontend polls
``unread_count`` frequently and the message list only while a panel is open.
"""
from __future__ import annotations

from datetime import UTC, datetime

from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.permissions import FrontOffice, MFAVerified, StaffOnly

from .models import StaffChatCursor, StaffMessage
from .serializers import StaffMessageSerializer

_BROADCAST_AUDIENCES = frozenset(
    {StaffMessage.Audience.TEACHERS, StaffMessage.Audience.TUTORS, StaffMessage.Audience.ALL_STAFF}
)
# A cursor with no prior read is backdated to the epoch (not "now") so a
# staff member's very first unread-count check still counts messages sent
# before they ever opened the panel.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _role_audience_filter(user) -> Q:
    q = Q(audience=StaffMessage.Audience.ALL_STAFF)
    role = getattr(user, "role", None)
    if role == Role.TEACHER:
        q |= Q(audience=StaffMessage.Audience.TEACHERS)
    if role == Role.TUTOR:
        q |= Q(audience=StaffMessage.Audience.TUTORS)
    return q


def _inbox_filter(user) -> Q:
    """Direct messages to/from this user, plus broadcasts aimed at their role."""
    return Q(recipient=user) | Q(sender=user) | _role_audience_filter(user)


class StaffMessageViewSet(viewsets.ModelViewSet):
    """Append-only: no edit, no delete — this is a log of what was said, like
    an incident hand-off, not a document to revise after the fact."""

    serializer_class = StaffMessageSerializer
    permission_classes = [StaffOnly, MFAVerified]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        qs = StaffMessage.objects.select_related("sender", "recipient")
        role = getattr(user, "role", None)
        if role in (Role.SUPERADMIN, Role.ADMIN, Role.FRONT_DESK):
            return qs
        return qs.filter(_inbox_filter(user)).distinct()

    def perform_create(self, serializer):
        audience = serializer.validated_data.get("audience", StaffMessage.Audience.DIRECT)
        if audience in _BROADCAST_AUDIENCES and not FrontOffice().has_permission(
            self.request, self
        ):
            self.permission_denied(
                self.request, message="Only front office may message a whole role at once."
            )
        recipient = serializer.validated_data.get("recipient")
        if recipient is not None and getattr(recipient, "role", None) not in (
            Role.SUPERADMIN,
            Role.ADMIN,
            Role.FRONT_DESK,
            Role.TEACHER,
            Role.TUTOR,
        ):
            self.permission_denied(self.request, message="Staff chat is staff-only.")
        serializer.save(sender=self.request.user)

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        cursor, _ = StaffChatCursor.objects.get_or_create(
            user=request.user, defaults={"last_read_at": _EPOCH}
        )
        count = (
            StaffMessage.objects.filter(_inbox_filter(request.user))
            .exclude(sender=request.user)
            .filter(created_at__gt=cursor.last_read_at)
            .count()
        )
        return Response({"unread": count})

    @action(detail=False, methods=["post"])
    def mark_read(self, request):
        StaffChatCursor.objects.update_or_create(
            user=request.user, defaults={"last_read_at": timezone.now()}
        )
        return Response({"unread": 0})
