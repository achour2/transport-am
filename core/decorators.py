from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def role_requis(*roles):
    """Chaque page vérifie le rôle avant d'afficher quoi que ce soit."""

    def decorateur(vue):
        @wraps(vue)
        def enveloppe(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.role not in roles:
                raise PermissionDenied
            return vue(request, *args, **kwargs)

        return enveloppe

    return decorateur


client_requis = role_requis("client")
transporteur_requis = role_requis("transporteur")
admin_requis = role_requis("admin")
