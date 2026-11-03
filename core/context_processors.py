from .models import Parametres


def site(request):
    from django.conf import settings

    ctx = {"parametres": Parametres.charger(), "site_url": settings.SITE_URL.rstrip("/"),
           "paiement_en_ligne": settings.PAIEMENT_EN_LIGNE}
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        ctx["notifs_non_lues"] = user.notifications.filter(lue=False).count()
    return ctx
