from __future__ import annotations

from rest_framework import serializers

from .models import AttendanceRecord


class AttendanceRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.display_name", read_only=True)
    is_checked_in = serializers.BooleanField(read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = [
            "id", "student", "student_name", "group", "date", "status",
            "checked_in_at", "checked_in_by", "dropped_off_by_name",
            "checked_out_at", "checked_out_by", "collected_by_pickup",
            "collected_by_guardian", "collected_by_name", "note", "is_checked_in",
        ]
        read_only_fields = [
            "checked_in_at", "checked_in_by", "checked_out_at", "checked_out_by",
            "collected_by_pickup", "collected_by_guardian", "collected_by_name",
        ]


class CheckInSerializer(serializers.Serializer):
    student = serializers.UUIDField()
    group = serializers.UUIDField()
    date = serializers.DateField(required=False)
    dropped_off_by_name = serializers.CharField(required=False, allow_blank=True, default="")
    late = serializers.BooleanField(required=False, default=False)


class CheckOutSerializer(serializers.Serializer):
    pickup_id = serializers.UUIDField(required=False)
    guardian_link_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if not attrs.get("pickup_id") and not attrs.get("guardian_link_id"):
            raise serializers.ValidationError("Name a pickup person or a guardian.")
        return attrs


class MarkAbsentSerializer(serializers.Serializer):
    student = serializers.UUIDField()
    group = serializers.UUIDField()
    date = serializers.DateField(required=False)
    excused = serializers.BooleanField(required=False, default=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")
