from rest_framework.routers import SimpleRouter

from .views import (
    CreditViewSet,
    FeeScheduleViewSet,
    InvoiceLineViewSet,
    InvoiceViewSet,
    PaymentViewSet,
)

router = SimpleRouter()
router.register("fee-schedules", FeeScheduleViewSet, basename="fee-schedule")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("invoice-lines", InvoiceLineViewSet, basename="invoice-line")
router.register("payments", PaymentViewSet, basename="payment")
router.register("credits", CreditViewSet, basename="credit")

urlpatterns = router.urls
