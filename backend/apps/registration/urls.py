from rest_framework.routers import SimpleRouter

from .views import (
    ApplicationDocumentViewSet,
    ApplicationViewSet,
    ConsentViewSet,
    EnrolmentViewSet,
    OfferViewSet,
    WaitlistEntryViewSet,
)

router = SimpleRouter()
router.register("applications", ApplicationViewSet, basename="application")
router.register(
    "application-documents", ApplicationDocumentViewSet, basename="application-document"
)
router.register("waitlist", WaitlistEntryViewSet, basename="waitlist-entry")
router.register("offers", OfferViewSet, basename="offer")
router.register("enrolments", EnrolmentViewSet, basename="enrolment")
router.register("consents", ConsentViewSet, basename="consent")

urlpatterns = router.urls
