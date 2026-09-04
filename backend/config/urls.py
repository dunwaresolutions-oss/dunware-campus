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


def healthz(_request):
    return JsonResponse({"status": "ok", "service": "campus"})


api_patterns = [
    path("healthz/", healthz, name="healthz"),
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.people.urls")),
    path("", include("apps.health.urls")),
    path("", include("apps.registration.urls")),
    path("", include("apps.scheduling.urls")),
    path("", include("apps.attendance.urls")),
    path("", include("apps.lessons.urls")),
    path("", include("apps.communication.urls")),
    path("", include("apps.grades.urls")),
    path("", include("apps.booking.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include((api_patterns, "api"))),
]
