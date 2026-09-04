from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    label = "audit"
    verbose_name = "Campus - Audit"

    def ready(self):
        # Register every SensitiveModel subclass for automatic write-auditing,
        # then connect the CRUD signal receivers.
        from .registry import autodiscover_sensitive_models

        autodiscover_sensitive_models()
        from . import signals  # noqa: F401  (connects receivers)
