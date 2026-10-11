"""Campus Central -- production settings. Used by Campus-Central-Setup.exe
once that installer exists (C3 only builds the Django skeleton -- the
installer itself is a later, separate piece of work)."""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False

SILENCED_SYSTEM_CHECKS = ["security.W021"]

CORS_ALLOWED_ORIGINS = []
CORS_ALLOW_ALL_ORIGINS = False

AXES_ENABLED = True

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

if not env("CENTRAL_FIELD_ENCRYPTION_KEY", default=""):
    raise RuntimeError(
        "CENTRAL_FIELD_ENCRYPTION_KEY is not set. Campus Central will not start "
        "in production without it."
    )

CAMPUS_ADMIN_IP_ALLOWLIST = env.list("CAMPUS_ADMIN_IP_ALLOWLIST", default=["127.0.0.1"])
