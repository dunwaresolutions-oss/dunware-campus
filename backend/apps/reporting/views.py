"""Read-only operational endpoints for the console.

    GET /api/metrics/    role-scoped operational metrics (see metrics.py)
    GET /api/backups/    recorded backup / restore-verify runs (superadmin)

Staff + MFA. Neither is audited (aggregate / operational reads only).
"""
from __future__ import annotations

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import MFAVerified, StaffOnly, SuperadminOnly

from .metrics import build_metrics
from .models import BackupRun
from .serializers import BackupRunSerializer


class MetricsView(APIView):
    permission_classes = [IsAuthenticated, StaffOnly, MFAVerified]

    def get(self, request):
        return Response(build_metrics(request.user))


class BackupRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BackupRun.objects.select_related("triggered_by").all()
    serializer_class = BackupRunSerializer
    permission_classes = [IsAuthenticated, SuperadminOnly, MFAVerified]
