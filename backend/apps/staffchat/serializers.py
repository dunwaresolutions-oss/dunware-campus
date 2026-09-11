from __future__ import annotations

from rest_framework import serializers

from .models import StaffMessage


class StaffMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    recipient_name = serializers.SerializerMethodField()

    class Meta:
        model = StaffMessage
        fields = [
            "id",
            "sender",
            "sender_name",
            "recipient",
            "recipient_name",
            "audience",
            "body",
            "urgent",
            "created_at",
        ]
        read_only_fields = ["sender"]

    def get_sender_name(self, obj) -> str:
        u = obj.sender
        return (u.get_full_name() or u.username) if u else ""

    def get_recipient_name(self, obj) -> str:
        u = obj.recipient
        return (u.get_full_name() or u.username) if u else ""

    def validate(self, attrs):
        audience = attrs.get("audience", StaffMessage.Audience.DIRECT)
        recipient = attrs.get("recipient")
        if audience == StaffMessage.Audience.DIRECT and not recipient:
            raise serializers.ValidationError(
                {"recipient": "A direct message needs a recipient."}
            )
        if audience != StaffMessage.Audience.DIRECT and recipient:
            raise serializers.ValidationError(
                {"recipient": "A broadcast has no single recipient — leave this blank."}
            )
        return attrs
