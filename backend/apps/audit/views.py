"""
Read-only API over the append-only audit log. Admin tier only
(``AdminOnly`` = superadmin / admin), MFA-verified.

    GET /api/audit/            filtered, paged list, newest first
    GET /api/audit/summary/    counts by action for the last 24h (dashboard)

Reading the audit log is deliberately *not* itself audited — it would just
feed itself a page of READ rows every time someone scrolls.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.permissions import AdminOnly, MFAVerified

from .models import AuditEntry

# named shortcuts the console exposes as filter chips
_ACTION_SETS = {
    "security": ["LOGIN_FAILED", "LOCKOUT", "PERMISSION_DENIED"],
    "auth": ["LOGIN", "LOGOUT", "LOGIN_FAILED", "LOCKOUT", "MFA_ENROLLED", "MFA_VERIFIED"],
    "changes": ["CREATE", "UPDATE", "DELETE"],
    "reads": ["READ"],
    "governance": ["EXPORT", "ERASE"],
}


class AuditEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEntry
        fields = [
            "id", "at", "actor_label", "actor_role", "source_ip", "action",
            "object_type", "object_id", "summary", "changed_fields",
        ]


class AuditEntryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditEntrySerializer
    permission_classes = [IsAuthenticated, AdminOnly, MFAVerified]

    def get_queryset(self):
        qs = AuditEntry.objects.select_related("actor").order_by("-at")
        p = self.request.query_params

        preset = p.get("set")
        if preset in _ACTION_SETS:
            qs = qs.filter(action__in=_ACTION_SETS[preset])
        action_ = p.get("action")
        if action_:
            qs = qs.filter(action__in=[a for a in action_.split(",") if a])

        if p.get("actor"):
            qs = qs.filter(actor_id=p["actor"])
        if p.get("object_type"):
            qs = qs.filter(object_type=p["object_type"])
        if p.get("object_id"):
            qs = qs.filter(object_id=p["object_id"])

        term = (p.get("q") or "").strip()
        if term:
            qs = qs.filter(
                Q(summary__icontains=term)
                | Q(actor_label__icontains=term)
                | Q(object_type__icontains=term)
            )

        since = p.get("since")
        if since:
            dt = parse_datetime(since) or parse_date(since)
            if dt:
                qs = qs.filter(at__gte=dt)
        until = p.get("until")
        if until:
            dt = parse_datetime(until) or parse_date(until)
            if dt:
                qs = qs.filter(at__lte=dt)
        return qs

    @action(detail=False, methods=["get"])
    def summary(self, request):
        since = timezone.now() - timedelta(hours=24)
        base = AuditEntry.objects.filter(at__gte=since)
        return Response({
            "since": since,
            "login_failed": base.filter(action="LOGIN_FAILED").count(),
            "lockout": base.filter(action="LOCKOUT").count(),
            "permission_denied": base.filter(action="PERMISSION_DENIED").count(),
            "logins": base.filter(action="LOGIN").count(),
            "governance": base.filter(action__in=["EXPORT", "ERASE"]).count(),
            "total": base.count(),
        })
