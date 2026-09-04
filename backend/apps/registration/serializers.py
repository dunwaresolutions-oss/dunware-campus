from __future__ import annotations

from rest_framework import serializers

from .models import (
    Application,
    ApplicationDocument,
    Consent,
    Enrolment,
    Offer,
    WaitlistEntry,
)


class ApplicationSerializer(serializers.ModelSerializer):
    reviewed_by = serializers.PrimaryKeyRelatedField(read_only=True)
    student = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Application
        fields = [
            "id", "child_first_name", "child_last_name", "child_date_of_birth",
            "desired_start", "desired_group", "applicant_name", "applicant_email",
            "applicant_phone", "notes", "status", "submitted_at", "reviewed_by",
            "student", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "submitted_at"]


class ApplicationDocumentSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ApplicationDocument
        fields = ["id", "application", "title", "file", "uploaded_by", "created_at"]
        extra_kwargs = {"file": {"write_only": True}}


class WaitlistEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = WaitlistEntry
        fields = ["id", "application", "group", "priority", "added_at", "active"]


class OfferSerializer(serializers.ModelSerializer):
    made_by = serializers.PrimaryKeyRelatedField(read_only=True)
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Offer
        fields = ["id", "application", "group", "start_date", "expires_at",
                  "status", "made_by", "responded_at", "is_open", "created_at"]
        read_only_fields = ["status", "responded_at"]


class EnrolmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Enrolment
        fields = ["id", "student", "group", "start_date", "end_date", "status",
                  "source_application", "created_at"]
        read_only_fields = ["status"]


class ConsentSerializer(serializers.ModelSerializer):
    recorded_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Consent
        fields = ["id", "student", "kind", "version", "granted", "granted_by",
                  "granted_by_name", "recorded_at", "recorded_by", "notes", "created_at"]
