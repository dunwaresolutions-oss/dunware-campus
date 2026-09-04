from rest_framework.routers import SimpleRouter

from .views import (
    AvailabilityWindowViewSet,
    BookingViewSet,
    OfferingViewSet,
    SlotViewSet,
)

router = SimpleRouter()
router.register("offerings", OfferingViewSet, basename="offering")
router.register("availability-windows", AvailabilityWindowViewSet, basename="availability-window")
router.register("slots", SlotViewSet, basename="slot")
router.register("bookings", BookingViewSet, basename="booking")

urlpatterns = router.urls
