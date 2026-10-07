"""
Django settings for the Riwaq shop API.

Local development stays on SQLite and HTTP. Production PostgreSQL, HTTPS
cookies, and host lists come from environment variables.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def env_list_first(names, default=""):
    for name in names:
        raw = os.environ.get(name)
        if raw is not None and raw.strip():
            return env_list(name)
    return env_list("__unset__", default)


# development keeps the current local HTTP/SQLite setup.
# production forces DEBUG off and can point at PostgreSQL.
DJANGO_ENV = os.environ.get("DJANGO_ENV", "development").strip().lower()
PRODUCTION = DJANGO_ENV == "production"

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

DEBUG = False if PRODUCTION else env_bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

# Public browser origin. Used only as a fallback when the explicit origin lists are empty.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "").strip().rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "core",
    "shop",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "config.wsgi.application"

DB_ENGINE = os.environ.get("DB_ENGINE", "sqlite").strip().lower()

if DB_ENGINE in {"postgres", "postgresql"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["DB_NAME"],
            "USER": os.environ["DB_USER"],
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"

TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Asia/Hebron")

USE_I18N = True

USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

_local_origins = "http://127.0.0.1:5173,http://localhost:5173"
_origin_default = FRONTEND_URL or ("" if PRODUCTION else _local_origins)

CORS_ALLOWED_ORIGINS = env_list_first(
    ("DJANGO_CORS_ALLOWED_ORIGINS", "CORS_ALLOWED_ORIGINS"),
    _origin_default,
)
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = env_list_first(
    ("DJANGO_CSRF_TRUSTED_ORIGINS", "CSRF_TRUSTED_ORIGINS"),
    _origin_default,
)

# HTTPS flags stay off unless the operator turns them on.
# Local HTTP on 127.0.0.1 must keep insecure cookies.
USE_HTTPS = env_bool("DJANGO_USE_HTTPS", default=False)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", default=USE_HTTPS)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", default=USE_HTTPS)
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=False)

if USE_HTTPS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# HSTS is not implied by production mode. Enable it only after HTTPS is confirmed.
_hsts_seconds = os.environ.get("SECURE_HSTS_SECONDS", "").strip()
if USE_HTTPS and _hsts_seconds.isdigit() and int(_hsts_seconds) > 0:
    SECURE_HSTS_SECONDS = int(_hsts_seconds)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
    SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", default=False)
