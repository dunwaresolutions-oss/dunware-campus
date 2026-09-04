"""
Test settings — fast, hermetic, no external services.

Local `pytest` uses this (pyproject sets DJANGO_SETTINGS_MODULE). CI overrides
the env var to `config.settings.dev` so the same suite also runs against a real
PostgreSQL service — the two together catch both logic bugs and DB-specific
regressions.
"""
from .dev import *  # noqa: F401,F403
from .dev import env

# In-memory SQLite: the models are DB-agnostic through Phase 1.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# A throwaway 32-byte base64 key so EncryptedField round-trips in tests.
FIELD_ENCRYPTION_KEY = env(
    "FIELD_ENCRYPTION_KEY",
    default="MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=",
)

# Fast hashing; brute-force lockout off unless a test turns it on explicitly.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
AXES_ENABLED = False

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# No collectstatic in the test run: plain (non-manifest) static storage so the
# admin templates render without a staticfiles.json.
STORAGES = {
    **globals()["STORAGES"],
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Throttles get in the way of auth tests; individual tests re-enable as needed.
REST_FRAMEWORK = {  # noqa: F405
    **globals()["REST_FRAMEWORK"],
    "DEFAULT_THROTTLE_RATES": {"auth": None, "sensitive": None},
}

# Deterministic admin break-glass checks.
CAMPUS_ADMIN_IP_ALLOWLIST = ["127.0.0.1", "testserver"]
CAMPUS_ADMIN_REQUIRE_MFA = True
