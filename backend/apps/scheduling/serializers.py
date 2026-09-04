from __future__ import annotations

from rest_framework import serializers

from .models import (
    AcademicYear,
    Closure,
    Room,
    SessionOccurrence,
    SessionTemplate,
    Term,
)


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ["id", "name", "kind", "capacity", "active"]


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = ["id", "name", "start_date", "end_date", "is_current"]


class TermSerializer(serializers.ModelSerializer):
    class Meta:
        model = Term
        fields = ["id", "academic_year", "name", "kind", "start_date", "end_date"]


class ClosureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Closure
        fields = ["id", "start_date", "end_date", "reason", "group"]


class SessionTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionTemplate
        fields = ["id", "group", "term", "room", "staff", "weekday", "start_time",
                  "end_time", "title", "active"]


class SessionOccurrenceSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True)

    class Meta:
        model = SessionOccurrence
        fields = ["id", "template", "group", "group_name", "room", "room_name", "staff",
                  "date", "start_time", "end_time", "title", "status", "cancelled_reason"]


class RosterEntrySerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    student_number = serializers.CharField()
    display_name = serializers.CharField()
