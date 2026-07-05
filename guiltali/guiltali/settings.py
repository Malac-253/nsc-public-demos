"""Guiltali — party/trip coordination prototype (Brock Trip 2026 demo).

Modular-monolith friendly: the `party` app owns all domain models and is
importable on its own. Deployable to Render free tier (SQLite or Postgres
via DATABASE_URL).
"""
from __future__ import annotations

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "SECRET_KEY", "dev-only-insecure-key-change-me-on-render"
)
DEBUG = os.environ.get("DEBUG", "1") == "1"

ALLOWED_HOSTS = ["*"] if DEBUG else os.environ.get(
    "ALLOWED_HOSTS", ".onrender.com,localhost,127.0.0.1"
).split(",")

CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get(
        "CSRF_TRUSTED_ORIGINS", "https://*.onrender.com"
    ).split(",") if o
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "party",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "guiltali.urls"

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
                "party.context_processors.active_trip",
            ],
        },
    },
]

WSGI_APPLICATION = "guiltali.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS: list[dict] = []  # demo accounts use short shared-style passwords

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/New_York"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))

# Allow video uploads up to ~50 MB (Render/nginx may also impose limits).
DATA_UPLOAD_MAX_MEMORY_SIZE = 52_428_800
FILE_UPLOAD_MAX_MEMORY_SIZE = 52_428_800

# Optional: persist uploads to S3 (recommended on Render free tier — local disk is wiped on redeploy).
# Set these env vars in Render → Environment:
#   AWS_STORAGE_BUCKET_NAME, AWS_S3_REGION_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
# Optional: AWS_S3_CUSTOM_DOMAIN (CloudFront or bucket website URL)
if os.environ.get("AWS_STORAGE_BUCKET_NAME"):
    INSTALLED_APPS.append("storages")
    AWS_STORAGE_BUCKET_NAME = os.environ["AWS_STORAGE_BUCKET_NAME"].strip()
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "us-east-1").strip()
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_S3_ADDRESSING_STYLE = "virtual"
    # Private bucket + time-limited signed URLs — only pages your app renders (after login)
    # get working links; raw S3 object URLs return 403. Download/img/video still work.
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = int(os.environ.get("AWS_QUERYSTRING_EXPIRE", "86400"))  # 24h
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
    custom_domain = (os.environ.get("AWS_S3_CUSTOM_DOMAIN") or "").strip()
    if custom_domain:
        AWS_S3_CUSTOM_DOMAIN = custom_domain
        MEDIA_URL = f"https://{custom_domain}/"
    else:
        MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/"
    STORAGES["default"] = {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "trips_home"
LOGOUT_REDIRECT_URL = "login"

# Stay signed in: sessions last ~90 days and survive closing the browser.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 90
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
