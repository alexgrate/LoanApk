from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "insecure-dev-key")
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django_filters",
    "axes",
    "loans",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "loans.middleware.SecurityHeadersMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "loans.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "local.sqlite3",
    },
    "loans": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("LOANS_DB_NAME", "dash_loans"),
        "USER": os.getenv("LOANS_DB_USER", ""),
        "PASSWORD": os.getenv("LOANS_DB_PASSWORD", ""),
        "HOST": os.getenv("LOANS_DB_HOST", ""),
        "PORT": os.getenv("LOANS_DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {
            "connect_timeout": 10,
            "options": "-c search_path=public",
        },
    },
}

SAMPLE_DB = os.getenv("USE_SAMPLE_DB", "False").lower() == "true"
if SAMPLE_DB:
    DATABASES["loans"].update(
        {
            "NAME": os.getenv("SAMPLE_DB_NAME", "dash_loans_dev"),
            "USER": os.getenv("SAMPLE_DB_USER", os.getenv("USER", "postgres")),
            "PASSWORD": os.getenv("SAMPLE_DB_PASSWORD", ""),
            "HOST": os.getenv("SAMPLE_DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("SAMPLE_DB_PORT", "5432"),
        }
    )

DATABASE_ROUTERS = ["loans.routers.LoansRouter"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

EXPORT_INCLUDE_PII = os.getenv("EXPORT_INCLUDE_PII", "False").lower() == "true"


# --- Email, via Microsoft Graph -----------------------------------------------

# Password setup and reset links are the only mail this application sends.
#
# Delivery goes through the Graph API rather than SMTP, using app-only
# (client credentials) auth. loans/mail.py implements it as an ordinary Django
# email backend, so PasswordResetForm and send_mail() work unchanged - only the
# transport differs.
MS_GRAPH_TENANT_ID = os.getenv("MS_GRAPH_TENANT_ID", "")
MS_GRAPH_CLIENT_ID = os.getenv("MS_GRAPH_CLIENT_ID", "")
MS_GRAPH_CLIENT_SECRET = os.getenv("MS_GRAPH_CLIENT_SECRET", "")
# The mailbox messages are sent from. Must be a real mailbox in the tenant.
MS_GRAPH_SENDER = os.getenv("MS_GRAPH_SENDER", "")

# With Graph unconfigured, messages are written to the console instead of sent.
# That is what makes local development work with no mail account at all - and
# it is why serve.py refuses to start without these once DEBUG is off, since
# otherwise reset links would be silently swallowed in production.
if MS_GRAPH_TENANT_ID and MS_GRAPH_CLIENT_ID and MS_GRAPH_CLIENT_SECRET and MS_GRAPH_SENDER:
    EMAIL_BACKEND = "loans.mail.GraphEmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "") or MS_GRAPH_SENDER
PORTAL_NAME = "DashMFB Loan Reports"

# How long a setup or reset link stays valid. Django uses one setting for both.
# Three days is the compromise: long enough for someone who joins on a Friday,
# short enough that an intercepted mailbox is not a permanent way in.
PASSWORD_RESET_TIMEOUT = int(os.getenv("PASSWORD_RESET_TIMEOUT_DAYS", "3")) * 86400

# Password reset is an account-takeover route and django-axes only guards the
# login form. Requests are throttled per IP - see loans/emails.py.
PASSWORD_RESET_MAX_PER_HOUR = int(os.getenv("PASSWORD_RESET_MAX_PER_HOUR", "5"))

# --- Authentication hardening -------------------------------------------------

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=30)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "loans/locked_out.html"
AXES_SENSITIVE_PARAMETERS = []

SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True  

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False 
CSRF_COOKIE_SAMESITE = "Lax"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "True").lower() == "true"
    SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    if os.getenv("DJANGO_BEHIND_TLS_PROXY", "False").lower() == "true":
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
        USE_X_FORWARDED_HOST = True

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]


(BASE_DIR / "logs").mkdir(exist_ok=True)


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "audit": {"format": "%(asctime)s %(levelname)s %(message)s"},
    },
    "handlers": {
        "audit_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "audit.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 10,
            "formatter": "audit",
        },
        "console": {"class": "logging.StreamHandler", "formatter": "audit"},
    },
    "loggers": {
        "loans.audit": {
            "handlers": ["audit_file", "console"],
            "level": "INFO",
            "propagate": False,
        },

        "axes": {"handlers": ["audit_file", "console"], "level": "WARNING",
                 "propagate": False},
    },
}
