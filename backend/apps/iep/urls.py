from rest_framework.routers import SimpleRouter

from .views import (
    IEPAccommodationViewSet,
    IEPGoalViewSet,
    IEPReviewViewSet,
    IEPServiceViewSet,
    IEPViewSet,
)

router = SimpleRouter()
router.register("ieps", IEPViewSet, basename="iep")
router.register("iep-goals", IEPGoalViewSet, basename="iep-goal")
router.register("iep-accommodations", IEPAccommodationViewSet, basename="iep-accommodation")
router.register("iep-services", IEPServiceViewSet, basename="iep-service")
router.register("iep-reviews", IEPReviewViewSet, basename="iep-review")

urlpatterns = router.urls
