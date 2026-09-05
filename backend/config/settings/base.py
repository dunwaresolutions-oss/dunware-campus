"""
Campus — base settings, shared by every environment.

Security posture (see docs/PII_SECURITY.md) is defined HERE so it is on by
default and each environment only relaxes what it must (dev) or tightens
further (prod). `python manage.py check --deploy` must pass clean before any
package is built.
"""
import sys
from pathlib import Path

import environ

if getattr(sys, "frozen", False):
    # PyInstaller onedir build: everything the installer cares about (.env,
    # the exported frontend, staticfiles) lives next to campus-app.exe, not
    # wherever this bundled module happens to unpack to.
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent  # .../backend

env = environ.Env()
# BASE_DIR/.env if present (the installer writes it; dev copies .env.example)
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    env.read_env(str(_env_file))

# ── Core ───────────────────────────────────────────────────────────────────
SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["https://localhost"])

# 32-byte base64 key for AES-GCM field encryption (apps/core/fields.py).
# Never logged, never in the DB, never in the repo.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
ROOT_URLCONF = "config.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

# ── Applications ──────────────────────────────────────────────────────────
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "axes",
    "django_q",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.audit",
    "apps.people",
    "apps.health",
    "apps.registration",
    "apps.scheduling",
    "apps.attendance",
    "apps.lessons",
    "apps.grades",
    "apps.booking",
    "apps.communication",
    "apps.billing",
    "apps.reporting",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ── Middleware ────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",   # serves the exported frontend
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",           # MFA state per request
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.audit.middleware.AuditContextMiddleware",  # actor/IP for the audit log
    "apps.core.admin_guard.AdminBreakGlassMiddleware",  # /admin: superuser + MFA + IP allow-list
    "axes.middleware.AxesMiddleware",                # keep last
]

# ── Templates ─────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ── Database ──────────────────────────────────────────────────────────────
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://campus:campus@127.0.0.1:5432/campus",
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)

# ── Authentication / passwords ────────────────────────────────────────────
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",  # first: enforces lockout
    "django.contrib.auth.backends.ModelBackend",
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# django-axes — brute-force lockout.
AXES_FAILURE_LIMIT = env.int("AXES_FAILURE_LIMIT", default=5)
AXES_COOLOFF_TIME = env.int("AXES_COOLOFF_HOURS", default=1)  # hours
# Lock the (username, IP) pair — a wrong password from one client doesn't lock a
# whole site behind a NAT, but a spray against one account from many IPs still
# trips the per-username counter.
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_CALLABLE = "apps.accounts.lockout.lockout_response"
AXES_CLIENT_IP_CALLABLE = "apps.audit.middleware.axes_client_ip"

# ── DRF — deny by default; every viewset narrows further ──────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "auth": "10/min",
        "sensitive": "30/min",
    },
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    # Every PermissionDenied / NotAuthenticated is written to the audit log.
    "EXCEPTION_HANDLER": "apps.core.exceptions.audited_exception_handler",
}

# ── Sessions & cookies ───────────────────────────────────────────────────
SESSION_COOKIE_NAME = "campus_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = env.int("SESSION_IDLE_SECONDS", default=60 * 60 * 8)  # 8h hard cap
CSRF_COOKIE_HTTPONLY = False   # the SPA reads it to set the header
CSRF_COOKIE_SAMESITE = "Lax"

# ── Security headers (prod overrides SSL bits; dev leaves them off) ───────
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# ── Email (email only in v1 — no SMS) ───────────────────────────────────
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="campus@localhost")

# ── Static / media ──────────────────────────────────────────────────────
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# The Next.js `output: 'export'` build lands here and whitenoise serves it.
# In the source tree that's a sibling frontend/out; the installer copies the
# same export to frontend_out/ next to the frozen exe (see deploy/campus.spec
# and deploy/install.ps1).
if getattr(sys, "frozen", False):
    FRONTEND_EXPORT_DIR = BASE_DIR / "frontend_out"
else:
    FRONTEND_EXPORT_DIR = BASE_DIR.parent / "frontend" / "out"
STATICFILES_DIRS = [FRONTEND_EXPORT_DIR] if FRONTEND_EXPORT_DIR.exists() else []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))

# ── Background jobs ─────────────────────────────────────────────────────
Q_CLUSTER = {
    "name": "campus",
    "workers": env.int("Q_WORKERS", default=2),
    "timeout": 600,
    "retry": 900,
    "orm": "default",   # DB-backed broker — no Redis dependency in the bundle
    "catch_up": False,
}

# ── i18n / tz ──────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-ca"
TIME_ZONE = env("TIME_ZONE", default="America/Toronto")
USE_I18N = True
USE_TZ = True

# ── Campus feature toggles ─────────────────────────────────────────────
FEATURE_STUDENT_LOGINS = env.bool("FEATURE_STUDENT_LOGINS", default=False)
FEATURE_PAYMENTS_GATEWAY = env("FEATURE_PAYMENTS_GATEWAY", default="manual")

# ── Break-glass admin (enforced by apps.core.admin_guard) ──────────────
# The Django admin is not a day-to-day surface: it is reachable only by a
# superuser, from an allow-listed IP, with MFA satisfied. prod.py narrows the
# allow-list further from the installer's answer.
CAMPUS_ADMIN_IP_ALLOWLIST = env.list("CAMPUS_ADMIN_IP_ALLOWLIST", default=["127.0.0.1"])
CAMPUS_ADMIN_REQUIRE_MFA = env.bool("CAMPUS_ADMIN_REQUIRE_MFA", default=True)

# ── MFA (django-otp) ──────────────────────────────────────────────────
OTP_TOTP_ISSUER = env("OTP_TOTP_ISSUER", default="Campus")
# Staff cannot reach a sensitive endpoint until a TOTP device is confirmed and
# the current session is OTP-verified (apps.core.permissions.MFAVerified).

# ── Retention (days) — enforced by apps/reporting jobs ─────────────────
RETENTION_PAST_STUDENT_DAYS = env.int("RETENTION_PAST_STUDENT_DAYS", default=2555)
RETENTION_AUDIT_LOG_DAYS = env.int("RETENTION_AUDIT_LOG_DAYS", default=3650)

# ── Logging — a filter scrubs known PII field names before anything is written ──
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "pii_scrub": {"()": "apps.core.logging.PIIScrubFilter"},
    },
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["pii_scrub"],
            "formatter": "plain",
        },
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
