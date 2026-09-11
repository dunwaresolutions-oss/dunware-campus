from __future__ import annotations

from rest_framework import serializers

from .models import IEP, IEPAccommodation, IEPGoal, IEPReview, IEPService


class IEPGoalSerializer(serializers.ModelSerializer):
    class Meta:
        model = IEPGoal
        fields = ["id", "iep", "area", "description", "baseline", "target",
                  "progress", "progress_notes", "order", "created_at"]


class IEPAccommodationSerializer(serializers.ModelSerializer):
    class Meta:
        model = IEPAccommodation
        fields = ["id", "iep", "category", "description", "applies_to", "active",
                  "created_at"]


class IEPServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = IEPService
        fields = ["id", "iep", "service", "provider", "frequency", "location",
                  "start_date", "end_date", "notes", "created_at"]


class IEPReviewSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = IEPReview
        fields = ["id", "iep", "review_date", "attendees", "outcome", "notes",
                  "next_review_date", "recorded_by", "recorded_by_name", "created_at"]
        read_only_fields = ["recorded_by"]

    def get_recorded_by_name(self, obj) -> str:
        u = obj.recorded_by
        return (u.get_full_name() or u.username) if u else ""


class IEPSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.display_name", read_only=True)
    case_manager_name = serializers.SerializerMethodField()
    goal_count = serializers.IntegerField(source="iepgoals.count", read_only=True)
    goals = IEPGoalSerializer(source="iepgoals", many=True, read_only=True)
    accommodations = IEPAccommodationSerializer(
        source="iepaccommodations", many=True, read_only=True
    )
    services = IEPServiceSerializer(source="iepservices", many=True, read_only=True)
    reviews = IEPReviewSerializer(source="iepreviews", many=True, read_only=True)

    class Meta:
        model = IEP
        fields = [
            "id", "student", "student_name", "school_year", "status",
            "primary_concern", "start_date", "review_date", "end_date",
            "strengths", "needs", "summary", "case_manager", "case_manager_name",
            "created_by", "goal_count", "goals", "accommodations", "services",
            "reviews", "created_at", "updated_at",
        ]
        read_only_fields = ["created_by"]

    def get_case_manager_name(self, obj) -> str:
        u = obj.case_manager
        return (u.get_full_name() or u.username) if u else ""
