from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import StaffInvite, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "role", "is_active", "must_use_mfa", "last_login")
    list_filter = ("role", "is_active", "is_superuser")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Campus", {"fields": ("role", "must_use_mfa", "last_password_change")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Campus", {"fields": ("role",)}),
    )


@admin.register(StaffInvite)
class StaffInviteAdmin(admin.ModelAdmin):
    list_display = ("email", "role", "invited_by", "expires_at", "accepted_at")
    readonly_fields = ("token", "created_at", "accepted_at")
