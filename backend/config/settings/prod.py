"""
Production settings — used by the bundled installer.

The stack runs same-origin behind the bundled Caddy, which terminates HTTPS on
the LAN. Django trusts Caddy's X-Forwarded-Proto and serves session/CSRF
cookies as Secure. `manage.py check --deploy` must pass clean with this module.
"""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# Behind Caddy.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# HTTPS everywhere.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False  # LAN host, not a public domain -> no preload-list submission

# W021 warns that HSTS preload is off; that is intentional for a LAN appliance
# with an internal cert. Silenced so `check --deploy --fail-level WARNING`
# stays meaningful for real regressions.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

# Same-origin in production: the SPA is served by Django/whitenoise, so no CORS.
CORS_ALLOWED_ORIGINS = []
CORS_ALLOW_ALL_ORIGINS = False

# Lockout on.
AXES_ENABLED = True

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# Fail fast if the field-encryption key wasn't provisioned by the installer.
if not env("FIELD_ENCRYPTION_KEY", default=""):
    raise RuntimeError(
        "FIELD_ENCRYPTION_KEY is not set. The installer's first-run wizard "
        "generates it; Campus will not start in production without it."
    )

# Admin is break-glass only: superuser + MFA + IP allow-list (enforced in Phase 1).
CAMPUS_ADMIN_IP_ALLOWLIST = env.list("CAMPUS_ADMIN_IP_ALLOWLIST", default=["127.0.0.1"])
