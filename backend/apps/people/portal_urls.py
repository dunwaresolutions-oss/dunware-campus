from django.urls import path
from rest_framework.routers import SimpleRouter

from .portal_views import (
    ContactChangeRequestViewSet,
    PortalCalendarView,
    PortalConsentView,
    PortalDashboardView,
)

router = SimpleRouter()
router.register(
    "contact-change-requests", ContactChangeRequestViewSet, basename="contact-change-request"
)

urlpatterns = [
    path("dashboard/", PortalDashboardView.as_view(), name="portal-dashboard"),
    path("calendar/", PortalCalendarView.as_view(), name="portal-calendar"),
    path("consents/", PortalConsentView.as_view(), name="portal-consent"),
    *router.urls,
]
