"""
Campus Central -- base settings, shared by every environment.

Central is a SEPARATE Django project from Campus's own `config/`, with its
own database connection, its own entry points (manage_central.py / wsgi /
asgi) and its own trimmed INSTALLED_APPS -- never the school-operational
apps (people, health, registration, attendance, lessons, grades, iep,
booking, communication, staffchat, billing, reporting). That separation is
the whole point: Central's cross-school data must never sit in the same
database as any one school's live data (docs/CENTRAL_SYNC_SCOPE.md) -- a
compromised school install must never expose Central, and a Central
compromise must never expose a school's live system, only its own curated
copy of what was synced to it.

Reused as-is from Campus, by explicit design (Campus_MultiSchool_Action_Plan.html,
"Campus Central -- Build"): apps.core (BaseModel / SensitiveModel /
EncryptedField / the audit layer base classes), apps.accounts (User / Role /
MFA -- Central's own Ministry-staff accounts are rows in the SAME User model,
just in Central's own, separate database), apps.audit (Central's own
append-only audit of cross-school views/searches/exports). Reusing apps.core
wholesale also pulls in two Campus-specific, unused models (SchoolProfile,
SiteConfiguration) that create two harmless, always-empty tables in
Central's own database -- a known, accepted wart of the "same repo, shared
apps" approach, not a bug.
"""
import sys
from pathlib import Path

import environ

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent  # .../backend

env = environ.Env()
# BASE_DIR/.env.central if present -- kept deliberately distinct from Campus's
# own .env filename so the two can never be confused on a dev machine running
# both, or accidentally bundled into the wrong installer.
_env_file = BASE_DIR / ".env.central"
if _env_file.exists():
    env.read_env(str(_env_file))

# ── Core ───────────────────────────────────────────────────────────────────
SECRET_KEY = env("CENTRAL_SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["https://localhost"])

# 32-byte base64 key for AES-GCM field encryption (apps/core/fields.py) --
# Central's own key, never shared with any school's FIELD_ENCRYPTION_KEY.
FIELD_ENCRYPTION_KEY = env("CENTRAL_FIELD_ENCRYPTION_KEY", default="")

WSGI_APPLICATION = "central.wsgi.application"
ASGI_APPLICATION = "central.asgi.application"
ROOT_URLCONF = "central.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

# Same settings Campus's own config/settings/base.py defines, Central's own
# values -- see that file's comment for why this has to be settings-driven
# rather than apps.accounts importing one hardcoded role list. Lets the
# shared staff directory / invite endpoint (apps.accounts.UsersView /
# StaffInviteView) list and issue Central's three Ministry roles instead of
# Campus's STAFF_ROLES, with no new views needed (C8).
ACCOUNTS_DIRECTORY_ROLES = ["SUPERADMIN", "MINISTRY_ADMIN", "MINISTRY_ANALYST", "DISTRICT_OFFICER"]
# Who may invite a new Ministry account -- MINISTRY_ADMIN, same role that
# already owns registering a school / rotating a sync token
# (apps.central.permissions.MinistryAdminOnly). SUPERADMIN included for the
# same break-glass reason apps.central.permissions documents at length: the
# bootstrap account's role is literally "SUPERADMIN", not a Central role.
ACCOUNTS_INVITE_MANAGER_ROLES = ["SUPERADMIN", "MINISTRY_ADMIN"]

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
]

# Deliberately NOT the school-operational apps (people, health, registration,
# scheduling, attendance, lessons, grades, iep, booking, communication,
# staffchat, billing, reporting) -- Central never runs a school's own
# modules, only ingests a curated copy of what they produce.
LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.audit",
    "apps.central",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ── Middleware ────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.audit.middleware.AuditContextMiddleware",
    "apps.core.admin_guard.AdminBreakGlassMiddleware",
    "axes.middleware.AxesMiddleware",  # keep last
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

# ── Database -- Central's own, never a school's ────────────────────────────
DATABASES = {
    "default": env.db(
        "CENTRAL_DATABASE_URL",
        default="postgres://campus_central:campus_central@127.0.0.1:5432/campus_central",
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)

# ── Authentication / passwords ────────────────────────────────────────────
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
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

AXES_FAILURE_LIMIT = env.int("AXES_FAILURE_LIMIT", default=5)
AXES_COOLOFF_TIME = env.int("AXES_COOLOFF_HOURS", default=1)
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
    "EXCEPTION_HANDLER": "apps.core.exceptions.audited_exception_handler",
}

# ── Sessions & cookies -- distinct cookie name from Campus's own ──────────
SESSION_COOKIE_NAME = "campus_central_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = env.int("SESSION_IDLE_SECONDS", default=60 * 60 * 8)
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

# ── Security headers ───────────────────────────────────────────────────────
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# ── Email ───────────────────────────────────────────────────────────────
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="campus-central@localhost")

# ── Static / media ──────────────────────────────────────────────────────
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles_central"
# Central's own console is a separate, not-yet-built frontend (reusing the
# same component library as Campus's, per the plan -- but its own export,
# never Campus's build). Harmless no-op until that frontend exists.
if getattr(sys, "frozen", False):
    FRONTEND_EXPORT_DIR = BASE_DIR / "frontend_central_out"
else:
    FRONTEND_EXPORT_DIR = BASE_DIR.parent / "frontend_central" / "out"
STATICFILES_DIRS = [FRONTEND_EXPORT_DIR] if FRONTEND_EXPORT_DIR.exists() else []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = env("CENTRAL_MEDIA_ROOT", default=str(BASE_DIR / "media_central"))

# ── i18n / tz ──────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-ca"
TIME_ZONE = env("TIME_ZONE", default="America/Toronto")
USE_I18N = True
USE_TZ = True

# ── Break-glass admin (enforced by apps.core.admin_guard) ──────────────
# Same setting NAMES as Campus (the shared middleware reads these literally),
# own values.
CAMPUS_ADMIN_IP_ALLOWLIST = env.list("CAMPUS_ADMIN_IP_ALLOWLIST", default=["127.0.0.1"])
CAMPUS_ADMIN_REQUIRE_MFA = env.bool("CAMPUS_ADMIN_REQUIRE_MFA", default=True)

# ── MFA (django-otp) ──────────────────────────────────────────────────
OTP_TOTP_ISSUER = env("OTP_TOTP_ISSUER", default="Campus Central")

# ── Logging ──────────────────────────────────────────────────────────────
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
