"""Read-only metrics endpoint for the console dashboard.

    GET /api/metrics/   role-scoped operational metrics (see metrics.py)

Staff + MFA only. The payload is scoped to the caller's role — an instructor
gets numbers for their own groups, the office gets the school, admins get the
school plus system health. Not audited (aggregate reads only).
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import MFAVerified, StaffOnly

from .metrics import build_metrics


class MetricsView(APIView):
    permission_classes = [IsAuthenticated, StaffOnly, MFAVerified]

    def get(self, request):
        return Response(build_metrics(request.user))
