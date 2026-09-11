from rest_framework.routers import SimpleRouter

from .views import StaffMessageViewSet

router = SimpleRouter()
router.register("staff-messages", StaffMessageViewSet, basename="staff-message")

urlpatterns = router.urls
