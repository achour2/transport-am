import zoneinfo

from django import template
from django.utils import timezone

register = template.Library()

COULEURS_STATUT = {
    "enregistre": "secondary", "depose": "info", "charge": "info", "en_transit": "primary", "arrive": "warning",
    "livre": "success", "incident": "danger", "perdu": "dark", "annule": "light text-dark border",
    "planifie": "secondary", "en_cours": "primary", "termine": "success",
    "paye": "success", "en_attente": "warning", "echoue": "danger", "rembourse": "info",
    "ouvert": "danger", "retrouve": "success", "resolu": "success",
}


@register.filter
def couleur(statut):
    return COULEURS_STATUT.get(statut, "secondary")


@register.filter
def tz(valeur, fuseau):
    """Affiche une date dans le fuseau du pays concerné."""
    if not valeur:
        return valeur
    try:
        return timezone.localtime(valeur, zoneinfo.ZoneInfo(fuseau))
    except Exception:
        return timezone.localtime(valeur)


@register.filter
def nom_tz(fuseau):
    """Abréviation lisible du fuseau (ex. Africa/Algiers → Alger)."""
    villes = {"America/Toronto": "Montréal", "America/Montreal": "Montréal", "Africa/Algiers": "Alger",
              "Europe/Paris": "Paris", "Africa/Casablanca": "Casablanca", "Africa/Tunis": "Tunis"}
    return "heure de " + villes.get(fuseau, fuseau.split("/")[-1].replace("_", " "))


@register.filter
def depuis(valeur):
    if not valeur:
        return ""
    minutes = int((timezone.now() - valeur).total_seconds() // 60)
    if minutes < 1:
        return "à l'instant"
    if minutes < 60:
        return f"il y a {minutes} min"
    h = minutes // 60
    if h < 48:
        return f"il y a {h} h {minutes % 60:02d}"
    return f"il y a {h // 24} jours"


@register.filter
def argent(valeur, devise=""):
    try:
        txt = f"{float(valeur):,.2f}".replace(",", " ").replace(".", ",")
    except (TypeError, ValueError):
        return valeur
    if txt.endswith(",00"):
        txt = txt[:-3]
    symbole = {"CAD": "$", "USD": "$", "EUR": "€", "DZD": "DA", "MAD": "DH", "TND": "DT"}.get(devise, devise)
    return f"{txt} {symbole}".strip()


@register.simple_tag(takes_context=True)
def url_param(context, **kwargs):
    q = context["request"].GET.copy()
    for k, v in kwargs.items():
        q[k] = v
    return "?" + q.urlencode()
