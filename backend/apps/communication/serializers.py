from __future__ import annotations

from rest_framework import serializers

from .models import (
    Announcement,
    IncidentAcknowledgement,
    IncidentReport,
    Message,
    MessageTemplate,
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
    sender_name = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ["id", "thread", "sender", "sender_name", "body", "created_at"]

    def get_sender_name(self, obj) -> str:
        if not obj.sender_id:
            return ""
        return obj.sender.get_full_name() or obj.sender.username


class MessageThreadSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    messages = MessageSerializer(many=True, read_only=True)
    student_name = serializers.CharField(
        source="student.display_name", read_only=True, default=""
    )

    class Meta:
        model = MessageThread
        fields = ["id", "subject", "student", "student_name", "created_by", "participants",
                  "closed", "last_message_at", "messages", "created_at"]
        read_only_fields = ["last_message_at"]


class IncidentReportSerializer(serializers.ModelSerializer):
    reported_by = serializers.PrimaryKeyRelatedField(read_only=True)
    acknowledged_count = serializers.SerializerMethodField()
    student_name = serializers.CharField(source="student.display_name", read_only=True)

    class Meta:
        model = IncidentReport
        fields = ["id", "student", "student_name", "occurred_at", "location", "category",
                  "severity", "description", "action_taken", "first_aid_given",
                  "reported_by", "status", "guardians_notified_at", "acknowledged_count",
                  "created_at"]
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


class MessageTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageTemplate
        fields = ["id", "key", "name", "kind", "subject", "body", "description",
                  "active", "is_system", "updated_at"]
        read_only_fields = ["is_system"]

    def validate_key(self, value):
        inst = getattr(self, "instance", None)
        if inst and inst.is_system and value != inst.key:
            raise serializers.ValidationError("A system template's key can't change.")
        return value
