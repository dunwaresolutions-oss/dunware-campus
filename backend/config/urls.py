"""
Campus root URLconf.

  /api/            DRF API (every app registers its router here)
  /api/auth/       session login / logout / whoami / MFA
  /admin/          break-glass Django admin (superuser + MFA + IP allow-list)
  /                the exported Next.js SPA (served by whitenoise in prod)
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from apps.core.search import SearchView
from apps.core.views import RemoteAccessStatusView


def healthz(_request):
    return JsonResponse({"status": "ok", "service": "campus"})


api_patterns = [
    path("healthz/", healthz, name="healthz"),
    path("search/", SearchView.as_view(), name="search"),
    path("remote-access/status/", RemoteAccessStatusView.as_view(), name="remote-access-status"),
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.audit.urls")),
    path("", include("apps.people.urls")),
    path("", include("apps.health.urls")),
    path("", include("apps.registration.urls")),
    path("", include("apps.scheduling.urls")),
    path("", include("apps.attendance.urls")),
    path("", include("apps.lessons.urls")),
    path("", include("apps.communication.urls")),
    path("", include("apps.grades.urls")),
    path("", include("apps.booking.urls")),
    path("", include("apps.billing.urls")),
    path("portal/", include("apps.people.portal_urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include((api_patterns, "api"))),
]
