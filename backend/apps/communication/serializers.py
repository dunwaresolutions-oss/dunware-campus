from __future__ import annotations

from rest_framework import serializers

from .models import (
    Announcement,
    IncidentAcknowledgement,
    IncidentReport,
    Message,
    MessageThread,
    OutboundEmail,
)


class AnnouncementSerializer(serializers.ModelSerializer):
    author = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Announcement
        fields = ["id", "title", "body", "audience", "group", "author", "pinned",
                  "published_at", "email_sent_at", "created_at"]
        read_only_fields = ["published_at", "email_sent_at"]


class MessageSerializer(serializers.ModelSerializer):
    sender = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Message
        fields = ["id", "thread", "sender", "body", "created_at"]


class MessageThreadSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = MessageThread
        fields = ["id", "subject", "student", "created_by", "participants", "closed",
                  "last_message_at", "messages", "created_at"]
        read_only_fields = ["last_message_at"]


class IncidentReportSerializer(serializers.ModelSerializer):
    reported_by = serializers.PrimaryKeyRelatedField(read_only=True)
    acknowledged_count = serializers.SerializerMethodField()

    class Meta:
        model = IncidentReport
        fields = ["id", "student", "occurred_at", "location", "category", "severity",
                  "description", "action_taken", "first_aid_given", "reported_by",
                  "status", "guardians_notified_at", "acknowledged_count", "created_at"]
        read_only_fields = ["status", "guardians_notified_at"]

    def get_acknowledged_count(self, obj) -> int:
        return obj.acknowledgements.count()


class IncidentAcknowledgementSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncidentAcknowledgement
        fields = ["id", "incident", "guardian", "acknowledged_by", "signature_name",
                  "note", "created_at"]
        read_only_fields = ["acknowledged_by"]


class OutboundEmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutboundEmail
        fields = ["id", "kind", "subject", "to", "object_type", "object_id",
                  "sent_at", "error", "created_at"]
