from rest_framework import serializers

from .models import User


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
