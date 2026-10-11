"""
Campus Central root URLconf.

  /api/            DRF API
  /api/auth/       session login / logout / whoami / MFA / first-admin setup
                   (apps.accounts.urls, reused as-is -- it's a generic
                   account-management surface, nothing Campus-school-specific)
  /api/            audit log (apps.audit.urls)
  /api/central/    sync ingest (apps.central.urls, C4) -- bearer-token auth,
                   never a browser session
  /admin/          break-glass Django admin (superuser + MFA + IP allow-list)

No school-registry or dashboard endpoints yet (C6).
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthz(_request):
    return JsonResponse({"status": "ok", "service": "campus-central"})


api_patterns = [
    path("healthz/", healthz, name="healthz"),
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.audit.urls")),
    path("central/", include("apps.central.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include((api_patterns, "api"))),
]
