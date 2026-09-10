from __future__ import annotations

from rest_framework import serializers

from apps.core.models import SchoolProfile


class SchoolProfileSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    address_block = serializers.CharField(read_only=True)

    class Meta:
        model = SchoolProfile
        fields = [
            "name", "legal_name", "motto",
            "address_line1", "address_line2", "city", "region",
            "postal_code", "country", "address_block",
            "phone", "email", "website",
            "principal_name", "principal_title",
            "logo", "logo_url", "report_card_footer",
            "updated_at",
        ]
        extra_kwargs = {"logo": {"write_only": True, "required": False}}

    def get_logo_url(self, obj) -> str | None:
        if not obj.logo:
            return None
        request = self.context.get("request")
        url = obj.logo.url
        return request.build_absolute_uri(url) if request else url
