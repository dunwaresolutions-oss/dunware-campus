"""Campus Central -- development settings."""
from .base import *  # noqa: F401,F403
from .base import INSTALLED_APPS, env

DEBUG = env.bool("DEBUG", default=True)

STORAGES = {
    **globals()["STORAGES"],
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

INSTALLED_APPS += ["django_extensions"]

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:3100", "http://127.0.0.1:3100"],
)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:3100", "http://localhost:8002"],
)

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

AXES_ENABLED = env.bool("AXES_ENABLED", default=False)

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

REST_FRAMEWORK = {  # noqa: F405
    **globals()["REST_FRAMEWORK"],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}
