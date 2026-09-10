from __future__ import annotations

from rest_framework import serializers

from .models import BackupRun


class BackupRunSerializer(serializers.ModelSerializer):
    triggered_by_label = serializers.SerializerMethodField()
    duration_seconds = serializers.FloatField(read_only=True)

    class Meta:
        model = BackupRun
        fields = [
            "id", "kind", "status", "started_at", "finished_at",
            "duration_seconds", "archive_name", "size_bytes", "database_ok",
            "media_ok", "encrypted", "archives_retained", "error", "host",
            "build", "triggered_by", "triggered_by_label", "created_at",
        ]

    def get_triggered_by_label(self, obj) -> str:
        u = obj.triggered_by
        if u is None:
            return ""
        return u.get_full_name() or u.username
