from rest_framework.routers import SimpleRouter

from .views import (
    AssessmentResultViewSet,
    AssessmentSchemeViewSet,
    AssessmentViewSet,
    ReportCardEntryViewSet,
    ReportCardViewSet,
    RubricCriterionViewSet,
    RubricScoreViewSet,
)

router = SimpleRouter()
router.register("assessment-schemes", AssessmentSchemeViewSet, basename="assessment-scheme")
router.register("rubric-criteria", RubricCriterionViewSet, basename="rubric-criterion")
router.register("assessments", AssessmentViewSet, basename="assessment")
router.register("assessment-results", AssessmentResultViewSet, basename="assessment-result")
router.register("rubric-scores", RubricScoreViewSet, basename="rubric-score")
router.register("report-cards", ReportCardViewSet, basename="report-card")
router.register("report-card-entries", ReportCardEntryViewSet, basename="report-card-entry")

urlpatterns = router.urls
