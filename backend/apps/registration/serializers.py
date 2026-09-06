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


def _application_child_name(application) -> str:
    if application is None:
        return ""
    return f"{application.child_first_name} {application.child_last_name}".strip()


class WaitlistEntrySerializer(serializers.ModelSerializer):
    child_name = serializers.SerializerMethodField()
    group_name = serializers.CharField(source="group.name", read_only=True)

    class Meta:
        model = WaitlistEntry
        fields = ["id", "application", "child_name", "group", "group_name",
                  "priority", "added_at", "active"]

    def get_child_name(self, obj) -> str:
        return _application_child_name(obj.application)


class OfferSerializer(serializers.ModelSerializer):
    made_by = serializers.PrimaryKeyRelatedField(read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    child_name = serializers.SerializerMethodField()
    group_name = serializers.CharField(source="group.name", read_only=True)

    class Meta:
        model = Offer
        fields = ["id", "application", "child_name", "group", "group_name",
                  "start_date", "expires_at", "status", "made_by", "responded_at",
                  "is_open", "created_at"]
        read_only_fields = ["status", "responded_at"]

    def get_child_name(self, obj) -> str:
        return _application_child_name(obj.application)


class EnrolmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.display_name", read_only=True)
    group_name = serializers.CharField(source="group.name", read_only=True)

    class Meta:
        model = Enrolment
        fields = ["id", "student", "student_name", "group", "group_name",
                  "start_date", "end_date", "status", "source_application", "created_at"]
        read_only_fields = ["status"]


class ConsentSerializer(serializers.ModelSerializer):
    recorded_by = serializers.PrimaryKeyRelatedField(read_only=True)
    student_name = serializers.CharField(source="student.display_name", read_only=True)

    class Meta:
        model = Consent
        fields = ["id", "student", "student_name", "kind", "version", "granted",
                  "granted_by", "granted_by_name", "recorded_at", "recorded_by",
                  "notes", "created_at"]
