"""
Paramètres Django — Plateforme de transport de bagages.

Toutes les valeurs sensibles se règlent par variables d'environnement
(voir .env.example). Sans configuration, le projet démarre en mode
développement : SQLite, courriels affichés dans la console, paiement simulé.
"""
import os
from pathlib import Path

from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent


def env(nom, defaut=None):
    return os.environ.get(nom, defaut)


def env_bool(nom, defaut=False):
    return str(env(nom, defaut)).lower() in ("1", "true", "yes", "oui", "on")


# Charge un fichier .env simple (CLE=valeur) s'il existe
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    for ligne in _env_file.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("#") and "=" in ligne:
            cle, val = ligne.split("=", 1)
            os.environ.setdefault(cle.strip(), val.strip())

SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-changez-moi-en-production")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in env("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]

# Nom de domaine personnel (ex. DJANGO_DOMAINE=talaouglid.com) : ajoute domaine + www et l'adresse des courriels
DOMAINE = env("DJANGO_DOMAINE", "").strip().lower()
if DOMAINE:
    ALLOWED_HOSTS += [DOMAINE, f"www.{DOMAINE}"]
    CSRF_TRUSTED_ORIGINS += [f"https://{DOMAINE}", f"https://www.{DOMAINE}"]

# Hébergement Render : l'adresse publique est fournie automatiquement
RENDER_HOST = env("RENDER_EXTERNAL_HOSTNAME")
if RENDER_HOST:
    ALLOWED_HOSTS.append(RENDER_HOST)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_HOST}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "axes",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "core.securite.ExigerDoubleAuthAdmin",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Base de données : PostgreSQL si DATABASE_URL / POSTGRES_DB est défini, sinon SQLite
if env("DATABASE_URL"):
    import dj_database_url

    DATABASES = {"default": dj_database_url.parse(env("DATABASE_URL"), conn_max_age=600)}
elif env("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB"),
            "USER": env("POSTGRES_USER", "postgres"),
            "PASSWORD": env("POSTGRES_PASSWORD", ""),
            "HOST": env("POSTGRES_HOST", "localhost"),
            "PORT": env("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "core.Utilisateur"
AUTHENTICATION_BACKENDS = ["axes.backends.AxesStandaloneBackend", "django.contrib.auth.backends.ModelBackend"]

# Connexion : blocage 1 h après 5 échecs pour le même compte depuis la même adresse IP (django-axes)
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "comptes/bloque.html"
AXES_CLIENT_IP_CALLABLE = "core.securite.ip_client_axes"
AXES_USERNAME_FORM_FIELD = "username"

# Double authentification obligatoire pour les administrateurs (DJANGO_ADMIN_2FA=false en cas d'urgence)
ADMIN_2FA = env_bool("DJANGO_ADMIN_2FA", True)
OTP_TOTP_ISSUER = "Talaouglid"
LOGIN_URL = "connexion"
LOGIN_REDIRECT_URL = "redirection_role"
LOGOUT_REDIRECT_URL = "accueil"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Langues : français par défaut, anglais et arabe (droite à gauche)
LANGUAGE_CODE = "fr"
LANGUES_DISPONIBLES = [("fr", "Français"), ("en", "English"), ("ar", "العربية")]
# Langues proposées aux visiteurs. Anglais et arabe masqués tant que la traduction n'est pas complète :
# DJANGO_LANGUES=fr,en,ar pour les réactiver.
_langues = [c.strip() for c in env("DJANGO_LANGUES", "fr").split(",") if c.strip()]
LANGUAGES = [l for l in LANGUES_DISPONIBLES if l[0] in _langues] or [LANGUES_DISPONIBLES[0]]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
# Dates enregistrées en UTC, affichées dans le fuseau du pays concerné
TIME_ZONE = env("DJANGO_TIME_ZONE", "America/Toronto")
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Fichiers statiques servis par WhiteNoise (compressés, mis en cache)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
# Tests : pas besoin de collectstatic
import sys as _sys

if "test" in _sys.argv:
    STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
    LIMITE_REQUETES_ACTIVE = False
# Photos servies par Django quand il n'y a ni Nginx ni S3 (ex. Render)
SERVE_MEDIA = env_bool("SERVE_MEDIA", False)

# Stockage S3 (OVHcloud Object Storage ou AWS S3) si configuré
if env("S3_BUCKET"):
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": env("S3_BUCKET"),
                "endpoint_url": env("S3_ENDPOINT_URL"),
                "access_key": env("S3_ACCESS_KEY"),
                "secret_key": env("S3_SECRET_KEY"),
                "region_name": env("S3_REGION", "auto"),
                "querystring_auth": True,  # liens temporaires signés : les photos restent privées
                "file_overwrite": False,
                "location": "media",
            },
        },
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Courriels : SMTP (Brevo / SendGrid) si EMAIL_HOST est défini, sinon console
if env("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST")
    EMAIL_PORT = int(env("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Talaouglid <no-reply@talaouglid.com>")

# Adresse publique du site (pour les liens dans les courriels)
SITE_URL = env("SITE_URL", f"https://{DOMAINE}" if DOMAINE else (f"https://{RENDER_HOST}" if RENDER_HOST else "http://localhost:8000"))

# Stripe : laissez vide pour le mode « paiement simulé » (démo / développement)
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", "")
STRIPE_PUBLIC_KEY = env("STRIPE_PUBLIC_KEY", "")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", "")
# Paiement par carte sur le site. Désactivé (= réservation en ligne, paiement au comptoir)
# tant que Stripe n'est pas configuré, sauf si PAIEMENT_EN_LIGNE=true (mode démo / développement).
PAIEMENT_EN_LIGNE = env_bool("PAIEMENT_EN_LIGNE", bool(STRIPE_SECRET_KEY))

# Vérifications périodiques (rappels 2 h, alertes 4 h, réservations expirées) :
# un service externe (cron-job.org) appelle /taches/verifications/ toutes les 10 min avec ce jeton.
VERIFICATIONS_JETON = env("VERIFICATIONS_JETON", "")

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

# Sécurité en production
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"core": {"handlers": ["console"], "level": "INFO"}},
}

# Alertes d'erreurs (Sentry, gratuit) : activé seulement si SENTRY_DSN est défini.
# Aucune donnée personnelle n'est envoyée (send_default_pii=False).
if env("SENTRY_DSN"):
    import sentry_sdk

    sentry_sdk.init(dsn=env("SENTRY_DSN"), send_default_pii=False, traces_sample_rate=0.0,
                    environment="production" if not DEBUG else "developpement")
