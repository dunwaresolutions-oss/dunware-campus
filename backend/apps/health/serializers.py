from __future__ import annotations

from rest_framework import serializers

from .models import (
    ActionPlan,
    Allergy,
    Condition,
    HealthAccessGrant,
    HealthProfile,
    Medication,
)


class HealthAccessGrantSerializer(serializers.ModelSerializer):
    granted_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = HealthAccessGrant
        fields = ["id", "user", "granted_by", "reason", "active", "created_at"]


class HealthProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthProfile
        fields = ["id", "student", "blood_type", "notes", "last_reviewed_at",
                  "reviewed_by", "created_at", "updated_at"]


class AllergySerializer(serializers.ModelSerializer):
    class Meta:
        model = Allergy
        fields = ["id", "student", "allergen", "reaction", "severity",
                  "epipen_required", "created_at"]


class ConditionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Condition
        fields = ["id", "student", "name", "details", "diagnosed_on", "ongoing", "created_at"]


class MedicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Medication
        fields = ["id", "student", "name", "dose", "schedule", "route", "prn",
                  "prescriber", "starts_on", "ends_on", "created_at"]


class ActionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActionPlan
        fields = ["id", "student", "kind", "plan", "effective_from", "review_by",
                  "document", "created_at"]
