from rest_framework.routers import DefaultRouter

from .views import AuditEntryViewSet

router = DefaultRouter()
router.register("audit", AuditEntryViewSet, basename="audit")

urlpatterns = router.urls
