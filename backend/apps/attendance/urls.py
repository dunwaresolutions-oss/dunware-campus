from rest_framework.routers import SimpleRouter

from .views import AttendanceRecordViewSet

router = SimpleRouter()
router.register("attendance", AttendanceRecordViewSet, basename="attendance-record")

urlpatterns = router.urls
