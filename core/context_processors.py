from .models import Parametres


def site(request):
    ctx = {"parametres": Parametres.charger()}
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        ctx["notifs_non_lues"] = user.notifications.filter(lue=False).count()
    return ctx
