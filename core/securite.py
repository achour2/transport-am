"""Protections : adresse IP réelle, limitation de requêtes, double authentification des administrateurs."""
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import redirect


def ip_client(request):
    """IP du visiteur (Render place l'IP réelle en tête de X-Forwarded-For)."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


def ip_client_axes(request, *args, **kwargs):
    return ip_client(request)


def limite_requetes(cle, nombre=30, secondes=60):
    """Au-delà de `nombre` requêtes par IP sur `secondes`, réponse 429 (anti-robots)."""

    def decorateur(vue):
        @wraps(vue)
        def enveloppe(request, *args, **kwargs):
            if getattr(settings, "LIMITE_REQUETES_ACTIVE", True):
                compteur = f"limite:{cle}:{ip_client(request)}"
                cache.add(compteur, 0, secondes)
                try:
                    total = cache.incr(compteur)
                except ValueError:
                    cache.set(compteur, 1, secondes)
                    total = 1
                if total > nombre:
                    return HttpResponse("Trop de requêtes. Réessayez dans une minute.", status=429)
            return vue(request, *args, **kwargs)

        return enveloppe

    return decorateur


CHEMINS_LIBRES_2FA = ("/2fa/", "/deconnexion/", "/static/", "/media/", "/i18n/", "/favicon.ico")


class ExigerDoubleAuthAdmin:
    """Un administrateur doit valider un code à usage unique (application d'authentification) après connexion."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            getattr(settings, "ADMIN_2FA", True)
            and user is not None and user.is_authenticated
            and getattr(user, "role", "") == "admin"
            and not user.is_verified()
            and not request.path.startswith(CHEMINS_LIBRES_2FA)
        ):
            return redirect(f"/2fa/?next={request.get_full_path()}")
        return self.get_response(request)
