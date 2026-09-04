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
    # feature apps register their routers here in phases 2-7, e.g.:
    # path("", include("apps.people.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include((api_patterns, "api"))),
]
