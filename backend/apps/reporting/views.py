"""Operational endpoints for the console.

    GET  /api/metrics/       role-scoped operational metrics (see metrics.py)
    GET  /api/backups/       recorded backup / restore-verify runs (admin+)
    POST /api/backups/run/   take an on-demand encrypted backup now (admin+)

Staff + MFA. The reads are not audited (aggregate / operational only). The
on-demand backup records who triggered it on the BackupRun row.
"""
from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import AdminOnly, MFAVerified, StaffOnly

from . import backup_runner
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
    permission_classes = [IsAuthenticated, AdminOnly, MFAVerified]

    def list(self, request, *args, **kwargs):
        # An abandoned run should not sit as "Running" forever.
        backup_runner.reconcile_stale_runs()
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="run")
    def run(self, request):
        """Take an on-demand encrypted backup now (superadmin / admin).

        Body: ``{"passphrase": "..."}`` — used for this one run and never
        stored; omit it if the Campus App service already has
        CAMPUS_BACKUP_PASSPHRASE set. Returns the RUNNING row (202); poll
        ``GET /api/backups/`` for SUCCESS / FAILED.
        """
        backup_runner.reconcile_stale_runs()
        ok, why = backup_runner.can_run_now()
        if not ok:
            return Response({"detail": why}, status=status.HTTP_409_CONFLICT)
        passphrase = str(request.data.get("passphrase") or "").strip()
        try:
            run = backup_runner.start_manual_backup(
                user=request.user, passphrase=passphrase
            )
        except backup_runner.BackupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(run).data, status=status.HTTP_202_ACCEPTED)
