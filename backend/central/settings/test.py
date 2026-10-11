"""Campus Central -- test settings (in-memory SQLite, fast hashing).

Not used by the default `pytest` run (pyproject.toml points that at
`config.settings.test`, Campus's own) -- Central's tests run with an
explicit override so the two projects' tests never share a settings module
or a database:

    pytest apps/central --ds=central.settings.test
"""
from .dev import *  # noqa: F401,F403
from .dev import env

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

FIELD_ENCRYPTION_KEY = env(
    "CENTRAL_FIELD_ENCRYPTION_KEY",
    default="MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=",
)

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
AXES_ENABLED = False

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

STORAGES = {
    **globals()["STORAGES"],
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

REST_FRAMEWORK = {  # noqa: F405
    **globals()["REST_FRAMEWORK"],
    "DEFAULT_THROTTLE_RATES": {"auth": None, "sensitive": None},
}

CAMPUS_ADMIN_IP_ALLOWLIST = ["127.0.0.1", "testserver"]
CAMPUS_ADMIN_REQUIRE_MFA = True
