from django.contrib import admin

from .models import AuditEntry


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    """Read-only in the admin — the audit log is append-only."""

    list_display = (
        "at", "actor_label", "actor_role", "action",
        "object_type", "object_id", "summary",
    )
    list_filter = ("action", "actor_role", "object_type")
    search_fields = ("actor_label", "object_id", "summary", "source_ip")
    date_hierarchy = "at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
