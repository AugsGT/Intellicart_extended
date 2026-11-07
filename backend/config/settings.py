"""Django settings for Intellicart. Everything environment-specific comes from .env."""
import os
from datetime import timedelta
from pathlib import Path

from corsheaders.defaults import default_headers

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY is not set - copy .env.example to .env")

def env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

# ---- Security (strict unless DJANGO_DEBUG=True) --------------------------------------------
# Set TRUST_PROXY_HEADERS=True only when the app is behind a reverse proxy you control that
# overwrites X-Forwarded-For / X-Forwarded-Proto; otherwise clients could forge them.
TRUST_PROXY_HEADERS = env_bool("TRUST_PROXY_HEADERS", False)
if TRUST_PROXY_HEADERS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024  # no request body over 1 MB (the API takes small JSON only)

SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", not DEBUG)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "0" if DEBUG else "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = False

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    # Intellicart modules. Empty ones are filled in by later phases.
    "apps.accounts",
    "apps.products",
    "apps.categories",
    "apps.cart",
    "apps.orders",
    "apps.inventory",
    "apps.recommendations",
    "apps.customer_intelligence",
    "apps.demand_intelligence",
    "apps.ai_assistant",
    "apps.interventions",
    "apps.events",
    "apps.analytics",
    "apps.notifications",
    "apps.audit",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
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
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "intellicart"),
        "USER": os.getenv("DB_USER", "intellicart"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# `collectstatic` target (only the Django admin has static files; the storefront is served by nginx).
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
# The storefront sends its anonymous-cart key in this header.
CORS_ALLOW_HEADERS = [*default_headers, "x-session-id"]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    # Private by default: a view must opt in to being public.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["config.renderers.DecimalSafeJSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "config.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "config.exceptions.api_exception_handler",
    # Every endpoint is rate limited; the sensitive ones (login, register, assistants) have tighter limits of their own.
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle", "rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "300/min", "user": "600/min", "login": "10/min", "register": "20/hour", "assistant": "30/min"},
}

# Throttle counters live in the cache. With several server processes they must share one, so
# set CACHE_URL (for example the Redis URL) in production; a per-process cache is fine locally.
if os.getenv("CACHE_URL"):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": os.environ["CACHE_URL"]}}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

# ---- Event infrastructure -------------------------------------------------
# How events are delivered: "rabbitmq" (deployment) or "local" (development without RabbitMQ).
# See apps/events/transport.py.
EVENT_TRANSPORT = os.getenv("EVENT_TRANSPORT", "rabbitmq")

# RabbitMQ carries domain events (names kept from the FastAPI version).
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
EVENTS_EXCHANGE = "intellicart.events"
EVENTS_QUEUE = "intellicart.events.queue"
EVENTS_DLX = "intellicart.events.dlx"
EVENTS_DLQ = "intellicart.events.queue.dlq"
EVENTS_MAX_RETRIES = int(os.getenv("EVENTS_MAX_RETRIES", "3"))
# Optional: RabbitMQ management API, used only for queue depth on the System Health page.
RABBITMQ_MANAGEMENT_URL = os.getenv("RABBITMQ_MANAGEMENT_URL", "")
RABBITMQ_MANAGEMENT_USER = os.getenv("RABBITMQ_MANAGEMENT_USER", "")
RABBITMQ_MANAGEMENT_PASSWORD = os.getenv("RABBITMQ_MANAGEMENT_PASSWORD", "")

# Celery runs scheduled and background jobs; Redis is its broker and result store.
CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "False") == "True"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    # Sends events from the outbox table to RabbitMQ.
    "relay-outbox": {"task": "apps.events.tasks.relay_outbox", "schedule": 3.0},
    # Flags idle carts as abandoned (emits CART_ABANDONED).
    "scan-abandoned-carts": {"task": "apps.interventions.tasks.scan_abandoned_carts", "schedule": 60.0},
    # Checks demand for spikes and predicted stockouts.
    "detect-demand-signals": {"task": "apps.demand_intelligence.tasks.detect_demand_signals", "schedule": 900.0},
}

# ---- AI -------------------------------------------------------------------
# Ollama runs as its own local server; Django never loads model weights.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "30"))
OLLAMA_MESSAGE_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_MESSAGE_TIMEOUT_SECONDS", "10"))

# Minutes without cart activity before a cart counts as abandoned.
CART_ABANDONMENT_MINUTES = int(os.getenv("CART_ABANDONMENT_MINUTES", "15"))
# Let Ollama write recovery messages (checked, with fixed templates as the fallback).
RESCUE_USE_LLM = os.getenv("RESCUE_USE_LLM", "True") == "True"
