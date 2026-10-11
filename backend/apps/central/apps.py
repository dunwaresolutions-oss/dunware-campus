from django.apps import AppConfig


class CentralConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.central"
    label = "central"
    verbose_name = "Campus Central"
