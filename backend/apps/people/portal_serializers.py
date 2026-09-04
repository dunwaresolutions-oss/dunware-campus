from __future__ import annotations

from rest_framework import serializers

from .models import ContactChangeRequest


class ContactChangeRequestSerializer(serializers.ModelSerializer):
    requested_by = serializers.PrimaryKeyRelatedField(read_only=True)
    reviewed_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ContactChangeRequest
        fields = [
            "id", "requested_by", "guardian", "guardian_link", "field",
            "current_value", "proposed_value", "reason", "status",
            "reviewed_by", "reviewed_at", "review_note", "created_at",
        ]
        read_only_fields = [
            "guardian_link", "current_value", "status", "reviewed_by",
            "reviewed_at", "review_note",
        ]


class ContactChangeSubmitSerializer(serializers.Serializer):
    field = serializers.CharField()
    proposed_value = serializers.CharField(allow_blank=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    student = serializers.UUIDField(required=False)


class PortalConsentSerializer(serializers.Serializer):
    student = serializers.UUIDField()
    kind = serializers.CharField()
    granted = serializers.BooleanField()
    version = serializers.CharField(required=False, default="1")
    note = serializers.CharField(required=False, allow_blank=True, default="")
