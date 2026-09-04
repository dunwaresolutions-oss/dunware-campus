from rest_framework.routers import SimpleRouter

from .views import (
    AuthorizedPickupViewSet,
    DocumentViewSet,
    EmergencyContactViewSet,
    GroupStaffViewSet,
    GroupViewSet,
    GuardianLinkViewSet,
    GuardianViewSet,
    ObservationViewSet,
    StudentViewSet,
)

router = SimpleRouter()
router.register("groups", GroupViewSet, basename="group")
router.register("group-staff", GroupStaffViewSet, basename="group-staff")
router.register("students", StudentViewSet, basename="student")
router.register("guardians", GuardianViewSet, basename="guardian")
router.register("guardian-links", GuardianLinkViewSet, basename="guardian-link")
router.register("emergency-contacts", EmergencyContactViewSet, basename="emergency-contact")
router.register("authorized-pickups", AuthorizedPickupViewSet, basename="authorized-pickup")
router.register("observations", ObservationViewSet, basename="observation")
router.register("documents", DocumentViewSet, basename="document")

urlpatterns = router.urls
