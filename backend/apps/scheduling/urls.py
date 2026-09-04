from rest_framework.routers import SimpleRouter

from .views import (
    AcademicYearViewSet,
    ClosureViewSet,
    RoomViewSet,
    SessionOccurrenceViewSet,
    SessionTemplateViewSet,
    TermViewSet,
)

router = SimpleRouter()
router.register("rooms", RoomViewSet, basename="room")
router.register("academic-years", AcademicYearViewSet, basename="academic-year")
router.register("terms", TermViewSet, basename="term")
router.register("closures", ClosureViewSet, basename="closure")
router.register("session-templates", SessionTemplateViewSet, basename="session-template")
router.register("sessions", SessionOccurrenceViewSet, basename="session-occurrence")

urlpatterns = router.urls
