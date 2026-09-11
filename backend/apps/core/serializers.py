from __future__ import annotations

from rest_framework import serializers

from apps.core.models import SchoolProfile


class SchoolProfileSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    address_block = serializers.CharField(read_only=True)
    principal_user_name = serializers.SerializerMethodField()
    has_signature = serializers.SerializerMethodField()
    signature_url = serializers.SerializerMethodField()

    class Meta:
        model = SchoolProfile
        fields = [
            "name", "legal_name", "motto",
            "address_line1", "address_line2", "city", "region",
            "postal_code", "country", "address_block",
            "phone", "email", "website",
            "principal_name", "principal_title", "principal_user", "principal_user_name",
            "logo", "logo_url", "signature", "has_signature", "signature_url",
            "report_card_footer", "updated_at",
        ]
        extra_kwargs = {
            "logo": {"write_only": True, "required": False},
            "signature": {"write_only": True, "required": False},
        }

    def get_logo_url(self, obj) -> str | None:
        if not obj.logo:
            return None
        request = self.context.get("request")
        url = obj.logo.url
        return request.build_absolute_uri(url) if request else url

    def get_principal_user_name(self, obj) -> str:
        u = obj.principal_user
        return (u.get_full_name() or u.username) if u else ""

    def get_has_signature(self, obj) -> bool:
        return bool(obj.signature)

    def get_signature_url(self, obj) -> str | None:
        if not obj.signature:
            return None
        request = self.context.get("request")
        path = "/api/school-profile/signature/"
        return request.build_absolute_uri(path) if request else path
