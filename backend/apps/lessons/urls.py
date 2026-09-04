from rest_framework.routers import SimpleRouter

from .views import CurriculumUnitViewSet, LessonPlanViewSet, LessonResourceViewSet

router = SimpleRouter()
router.register("curriculum-units", CurriculumUnitViewSet, basename="curriculum-unit")
router.register("lesson-plans", LessonPlanViewSet, basename="lesson-plan")
router.register("lesson-resources", LessonResourceViewSet, basename="lesson-resource")

urlpatterns = router.urls
