from rest_framework.routers import SimpleRouter

from .views import (
    AnnouncementViewSet,
    IncidentAcknowledgementViewSet,
    IncidentReportViewSet,
    MessageThreadViewSet,
    MessageViewSet,
    OutboundEmailViewSet,
)

router = SimpleRouter()
router.register("announcements", AnnouncementViewSet, basename="announcement")
router.register("message-threads", MessageThreadViewSet, basename="message-thread")
router.register("messages", MessageViewSet, basename="message")
router.register("incident-reports", IncidentReportViewSet, basename="incident-report")
router.register(
    "incident-acknowledgements", IncidentAcknowledgementViewSet, basename="incident-ack"
)
router.register("outbound-emails", OutboundEmailViewSet, basename="outbound-email")

urlpatterns = router.urls
