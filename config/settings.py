import os

from dotenv import load_dotenv

from .base import *

load_dotenv()

def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", os.getenv("SECRET_KEY"))
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() in {"1", "true", "yes", "on"}
ROOT_URLCONF = "project.urls"
AUTH_USER_MODEL = "account.User"
WSGI_APPLICATION = "project.wsgi.application"
ASGI_APPLICATION = "project.asgi.application"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "localhost").split(",")
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW", False)

if os.getenv("DJANGO_TESTING", "").lower() in {"1", "true", "yes", "on"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "test.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", os.getenv("DATABASE_NAME")),
            "USER": os.getenv("POSTGRES_USER", os.getenv("DATABASE_USER")),
            "PASSWORD": os.getenv(
                "POSTGRES_PASSWORD",
                os.getenv("DATABASE_PASSWORD"),
            ),
            "HOST": os.getenv(
                "POSTGRES_HOST",
                os.getenv("DATABASE_HOST", "db"),
            ),
            "PORT": os.getenv(
                "POSTGRES_PORT",
                os.getenv("DATABASE_PORT", "5432"),
            ),
            "OPTIONS": {"sslmode": "require"},
        }
    }

SPECTACULAR_SETTINGS = {
    "TITLE": "API Sistema de Revistas",
    "DESCRIPTION": "Documentación de los endpoints del sistema.",
    "VERSION": "1.0.0",
}

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
