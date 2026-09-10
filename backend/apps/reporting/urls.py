from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import BackupRunViewSet, MetricsView

router = SimpleRouter()
router.register("backups", BackupRunViewSet, basename="backup-run")

urlpatterns = [
    path("metrics/", MetricsView.as_view(), name="metrics"),
    *router.urls,
]
