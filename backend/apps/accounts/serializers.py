from rest_framework import serializers

from .models import STAFF_ROLES, User


class WhoAmISerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "email", "role", "display_name", "must_use_mfa")

    def get_display_name(self, obj) -> str:
        return obj.get_full_name() or obj.username


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(style={"input_type": "password"}, trim_whitespace=False)
    otp = serializers.CharField(required=False, allow_blank=True)


class TOTPTokenSerializer(serializers.Serializer):
    """A 6-digit TOTP code (django-otp also accepts a static backup token)."""

    token = serializers.CharField(min_length=6, max_length=16, trim_whitespace=True)


class StaffInviteCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=[(r.value, r.label) for r in STAFF_ROLES])


class InviteAcceptSerializer(serializers.Serializer):
    token = serializers.CharField()
    username = serializers.CharField(min_length=3, max_length=150)
    password = serializers.CharField(
        style={"input_type": "password"}, trim_whitespace=False, min_length=12
    )


class SetupAdminSerializer(serializers.Serializer):
    """The browser's first-run form: create the initial SUPERADMIN."""

    username = serializers.CharField(min_length=3, max_length=150, trim_whitespace=True)
    email = serializers.EmailField()
    password = serializers.CharField(
        style={"input_type": "password"}, trim_whitespace=False, min_length=12
    )
