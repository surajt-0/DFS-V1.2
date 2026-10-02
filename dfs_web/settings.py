"""
Django settings for the Digital Forensics Browser Suite (web edition).
Agamya Cyber Tech.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Core / security
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "DFS_SECRET_KEY",
    "django-insecure-CHANGE-ME-before-any-real-deployment-000000000000",
)

DEBUG = env_bool("DFS_DEBUG", default=True)

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DFS_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]

CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get(
    "DFS_CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if o.strip()]

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    'rest_framework',
    'corsheaders',

    'accounts',
    'core',
    'cases',
    'evidence',
    'recovery',
    'auditlog',
    'dashboard',
    'billing',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Serves /static/ (needed for a styled Django admin) without relying on
    # `manage.py runserver`'s dev-only static serving -- matters once the
    # desktop build serves the app through waitress instead. WHITENOISE_USE_FINDERS
    # below lets it serve straight from app static dirs, no collectstatic required.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'auditlog.middleware.AuditLogMiddleware',
]

# ---------------------------------------------------------------------------
# React frontend (billing SPA) support: DRF session auth + CORS for the
# Vite dev server. The React app talks to the JSON API under /api/billing/
# using the same session cookie as the rest of the site, so users log in
# once (via /accounts/login/) and the SPA "just works" -- no token dance.
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
}

CORS_ALLOWED_ORIGINS = [o.strip() for o in os.environ.get(
    "DFS_CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if o.strip()]
CORS_ALLOW_CREDENTIALS = True

ROOT_URLCONF = 'dfs_web.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'dfs_web.context_processors.suite_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'dfs_web.wsgi.application'

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def env_path(name, default):
    """Like os.environ.get, but treats an unset OR blank value as 'use the
    default' -- .env.example documents these as blank-by-default, and a
    literal empty string would otherwise become an invalid path."""
    val = os.environ.get(name, "").strip()
    return val if val else str(default)


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        # Overridable so the desktop build (desktop_app.py) can point this at
        # a writable per-user data directory instead of the (often read-only,
        # temp-extracted) install location.
        'NAME': env_path("DFS_DB_PATH", BASE_DIR / 'db.sqlite3'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------------------
# i18n / tz
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
# The database always stores UTC (USE_TZ=True), so the underlying instant
# is never wrong -- but server-rendered display (Django admin's audit log
# list, exported CSV/XLSX timestamps, PDF report timestamps) all render in
# THIS timezone, not the browser's. Left at the default "UTC" it looked
# hours off from real time for anyone outside UTC+0. Override with the
# DFS_TIME_ZONE env var for other deployments/regions.
TIME_ZONE = os.environ.get("DFS_TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = Path(env_path("DFS_STATIC_ROOT", BASE_DIR / 'staticfiles'))
# Serve directly from static finders (app dirs + STATICFILES_DIRS) rather
# than requiring a collectstatic step before the desktop build works.
WHITENOISE_USE_FINDERS = True

MEDIA_URL = 'media/'
MEDIA_ROOT = Path(env_path("DFS_MEDIA_ROOT", BASE_DIR / 'media'))

# Where uploaded evidence originals + safe working copies live (kept out of MEDIA
# so nothing evidentiary is ever served through a public media URL by accident).
EVIDENCE_STORAGE_ROOT = Path(env_path("DFS_EVIDENCE_ROOT", BASE_DIR / "evidence_store"))
EVIDENCE_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Auth / redirects
# ---------------------------------------------------------------------------
# These matter only if something calls django.contrib.auth.views' redirect
# helpers directly; the SPA authenticates via the JSON API
# (accounts.api_urls) and never hits Django's own login/logout views, so
# these are plain fallback paths rather than reversed URL names.
LOGIN_URL = '/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------
MAX_UPLOAD_SIZE_MB = int(os.environ.get("DFS_MAX_UPLOAD_MB", "512"))
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5MB in-memory threshold; larger goes to temp file

# ---------------------------------------------------------------------------
# Session hardening (sensible defaults; tighten further behind HTTPS in prod)
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # JS reads it for AJAX header
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8-hour working session
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

SECURE_SSL_REDIRECT = env_bool("DFS_SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = env_bool("DFS_SECURE_COOKIES", default=False)
CSRF_COOKIE_SECURE = env_bool("DFS_SECURE_COOKIES", default=False)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# ---------------------------------------------------------------------------
# Suite-level config
# ---------------------------------------------------------------------------
SUITE_NAME = "Digital Forensics Browser Suite"
SUITE_ORG = "Agamya Cyber Tech"
SUITE_VERSION = "4.0 (Web Edition)"

# The "server-side scan" convenience feature (core/browser_detect.py) only
# makes sense when this Django app is run locally on an investigator's own
# workstation -- it inspects the filesystem of the machine running the
# server. Off by default; an admin running the suite locally can flip it on.
ENABLE_LOCAL_BROWSER_SCAN = env_bool("DFS_ENABLE_LOCAL_SCAN", default=False)

# On a paid plan (Pro/Enterprise), whether EVERY role -- admin, examiner and
# read-only reviewer -- may upload evidence (manually or via the automatic
# local scan) to cases they can see. True by default; set False to make
# evidence upload follow the stricter "must be allowed to edit the case"
# rule instead (viewers can then never upload). See core/permissions.py.
EVIDENCE_UPLOAD_ALL_ROLES = env_bool("DFS_EVIDENCE_UPLOAD_ALL_ROLES", default=True)

# ---------------------------------------------------------------------------
# Billing / subscriptions (Razorpay)
# ---------------------------------------------------------------------------
# Leave unset to run in demo mode: checkout still works end-to-end (orders,
# invoices, plan activation) but payments are simulated locally instead of
# hitting Razorpay. Set both to enable live payments; get them from
# https://dashboard.razorpay.com/app/keys
RAZORPAY_KEY_ID = os.environ.get("DFS_RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("DFS_RAZORPAY_KEY_SECRET", "")
# From the webhook config screen in the Razorpay dashboard; only needed if
# you set up a webhook pointing at /billing/webhook/razorpay/
RAZORPAY_WEBHOOK_SECRET = os.environ.get("DFS_RAZORPAY_WEBHOOK_SECRET", "")

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
