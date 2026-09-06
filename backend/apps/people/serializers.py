from __future__ import annotations

from rest_framework import serializers

from .models import (
    AuthorizedPickup,
    Document,
    EmergencyContact,
    Group,
    GroupStaff,
    Guardian,
    GuardianLink,
    Observation,
    Student,
)


class GroupSerializer(serializers.ModelSerializer):
    active_enrolment_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ["id", "name", "kind", "stage_label", "capacity", "active",
                  "active_enrolment_count", "created_at"]

    def get_active_enrolment_count(self, obj) -> int:
        return obj.enrolments.filter(status="ACTIVE").count()


class GroupStaffSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupStaff
        fields = ["id", "group", "user", "role", "active"]


class StudentSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    primary_group_name = serializers.CharField(source="primary_group.name", read_only=True)
    guardian_count = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            "id", "first_name", "last_name", "preferred_name", "display_name",
            "date_of_birth", "pronouns", "student_number", "government_id",
            "custody_notes", "status", "primary_group", "primary_group_name",
            "left_on", "legal_hold", "anonymized_at", "user",
            "guardian_count", "created_at", "updated_at",
        ]
        read_only_fields = ["anonymized_at"]
        extra_kwargs = {"student_number": {"required": False}}

    def get_guardian_count(self, obj) -> int:
        return obj.guardian_links.count()


class GuardianSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Guardian
        fields = ["id", "first_name", "last_name", "email", "phone", "address",
                  "user", "children", "created_at"]

    def get_children(self, obj) -> list[dict]:
        return [
            {
                "id": str(link.student_id),
                "name": link.student.display_name,
                "relationship": link.relationship,
            }
            for link in obj.links.select_related("student").all()
        ]


class GuardianLinkSerializer(serializers.ModelSerializer):
    guardian_name = serializers.CharField(source="guardian.__str__", read_only=True)

    class Meta:
        model = GuardianLink
        fields = [
            "id", "student", "guardian", "guardian_name", "relationship",
            "is_primary_contact", "has_custody", "can_pickup",
            "receives_communications", "lives_with", "custody_notes",
        ]


class EmergencyContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmergencyContact
        fields = ["id", "student", "name", "relationship", "phone", "alt_phone", "priority"]


class AuthorizedPickupSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthorizedPickup
        fields = ["id", "student", "name", "relationship", "phone", "note", "active"]


class ObservationSerializer(serializers.ModelSerializer):
    author = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Observation
        fields = ["id", "student", "author", "category", "occurred_at", "body",
                  "visible_to_guardians", "created_at"]


class DocumentSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.PrimaryKeyRelatedField(read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ["id", "student", "kind", "title", "file", "download_url",
                  "content_type", "byte_size", "uploaded_by", "created_at"]
        extra_kwargs = {"file": {"write_only": True}}

    def get_download_url(self, obj) -> str | None:
        request = self.context.get("request")
        if not obj.file:
            return None
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url

    def create(self, validated_data):
        upload = validated_data.get("file")
        if upload is not None:
            validated_data["byte_size"] = getattr(upload, "size", 0) or 0
            validated_data["content_type"] = getattr(upload, "content_type", "") or ""
        return super().create(validated_data)
