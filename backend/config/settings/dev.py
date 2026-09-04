"""Development settings — relaxes only what local work needs."""
from .base import *  # noqa: F401,F403
from .base import INSTALLED_APPS, env

DEBUG = env.bool("DEBUG", default=True)

INSTALLED_APPS += ["django_extensions"]

# Let the Next.js dev server (localhost:3000) call the API on :8001.
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:3000", "http://127.0.0.1:3000"],
)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:3000", "http://localhost:8001"],
)

# No HTTPS locally.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Axes off by default in dev so it doesn't lock you out while iterating.
AXES_ENABLED = env.bool("AXES_ENABLED", default=False)

# Show emails in the console.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Browsable API is handy in dev.
REST_FRAMEWORK = {  # noqa: F405
    **globals()["REST_FRAMEWORK"],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}
