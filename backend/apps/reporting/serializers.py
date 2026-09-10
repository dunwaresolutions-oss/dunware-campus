from __future__ import annotations

from rest_framework import serializers

from .models import BackupRun


class BackupRunSerializer(serializers.ModelSerializer):
    triggered_by_label = serializers.CharField(
        source="triggered_by.get_full_name", read_only=True, default=""
    )
    duration_seconds = serializers.FloatField(read_only=True)

    class Meta:
        model = BackupRun
        fields = [
            "id", "kind", "status", "started_at", "finished_at",
            "duration_seconds", "archive_name", "size_bytes", "database_ok",
            "media_ok", "encrypted", "archives_retained", "error", "host",
            "build", "triggered_by", "triggered_by_label", "created_at",
        ]
