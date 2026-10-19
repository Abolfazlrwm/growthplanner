"""Portable settings: managed MySQL, external PostgreSQL, or local SQLite."""
from pathlib import Path
import hashlib
import os
import json
import ssl
import environ

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env(DEBUG=(bool, False), ALLOWED_HOSTS=(list, []), CSRF_TRUSTED_ORIGINS=(list, []))
environ.Env.read_env(BASE_DIR / ".env")
_platform_signing_key = os.environ.get("MANUS_JWT_SECRET", "")
# Derive a domain-separated Django key without shadowing platform credentials.
SECRET_KEY = env("SECRET_KEY", default=hashlib.sha256(("growthplanner:django:v1:" + _platform_signing_key).encode()).hexdigest() if _platform_signing_key else "")
if not SECRET_KEY:
    raise RuntimeError("Set SECRET_KEY; see .env.example")
DEBUG = env("DEBUG")
MANAGED_HOSTING = bool(os.environ.get("MANUS_PROJECT_ID"))
ALLOWED_HOSTS = env("ALLOWED_HOSTS", default=["*"] if MANAGED_HOSTING else ["localhost", "127.0.0.1", "testserver"])
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS", default=["https://*.manus.computer", "https://*.manus.space"] if MANAGED_HOSTING else [])
PUBLIC_ORIGIN = env("PUBLIC_ORIGIN", default="").rstrip("/")
FRAME_ANCESTORS = env.list("FRAME_ANCESTORS", default=["'self'", "https://manus.im", "https://www.manus.im"] if MANAGED_HOSTING else ["'self'"])
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "rest_framework.authtoken", "drf_spectacular",
    "apps.core", "apps.accounts", "apps.goals", "apps.tasks", "apps.habits",
    "apps.journal", "apps.calendar_view", "apps.assistant",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.security.ApplicationSecurityMiddleware",
    "apps.core.middleware.UiPreferencesMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages", "apps.core.context_processors.ui",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)
if DATABASES["default"]["ENGINE"].endswith("mysql"):
    DATABASES["default"]["ENGINE"] = "config.db.backends.mysql"
    DATABASES["default"]["OPTIONS"].setdefault("charset", "utf8mb4")
    DATABASES["default"]["OPTIONS"].setdefault("init_command", "SET sql_mode='STRICT_TRANS_TABLES'")
    tls = DATABASES["default"]["OPTIONS"].get("ssl")
    if isinstance(tls, str):
        options = json.loads(tls)
        if options.get("rejectUnauthorized", True):
            DATABASES["default"]["OPTIONS"]["ssl"] = ssl.create_default_context()
        else:
            raise RuntimeError("Unverified database TLS is not supported")
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "fa"
LANGUAGES = [("fa", "فارسی"), ("en", "English")]
TIME_ZONE = "Asia/Tehran"
USE_I18N = USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage" if not DEBUG else "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication", "rest_framework.authentication.TokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle", "rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": "1000/hour", "anon": "50/hour"},
}
SPECTACULAR_SETTINGS = {
    "TITLE": "GrowthPlanner API", "DESCRIPTION": "User-scoped goals, tasks, habits and notes. Session or Token authentication.",
    "VERSION": "2.0.0", "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
}
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
AUTH_RATE_LIMIT = 30
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "accounts:login"
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="GrowthPlanner <no-reply@example.com>")
PASSWORD_RESET_ENABLED = DEBUG or EMAIL_BACKEND != "django.core.mail.backends.console.EmailBackend"
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not MANAGED_HOSTING)
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=604800)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    X_FRAME_OPTIONS = "DENY"
if MANAGED_HOSTING:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = CSRF_COOKIE_SAMESITE = "None"
    X_FRAME_OPTIONS = "ALLOWALL"
LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}
