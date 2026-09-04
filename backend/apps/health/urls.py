from rest_framework.routers import SimpleRouter

from .views import (
    ActionPlanViewSet,
    AllergyViewSet,
    ConditionViewSet,
    HealthAccessGrantViewSet,
    HealthProfileViewSet,
    MedicationViewSet,
)

router = SimpleRouter()
router.register("health/access-grants", HealthAccessGrantViewSet, basename="health-access-grant")
router.register("health/profiles", HealthProfileViewSet, basename="health-profile")
router.register("health/allergies", AllergyViewSet, basename="health-allergy")
router.register("health/conditions", ConditionViewSet, basename="health-condition")
router.register("health/medications", MedicationViewSet, basename="health-medication")
router.register("health/action-plans", ActionPlanViewSet, basename="health-action-plan")

urlpatterns = router.urls
