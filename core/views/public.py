"""Espace public (6.1) : accueil, destinations, simulateur, suivi, comptes, aide."""
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db.models import Min
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST

from ..forms import AbonnementForm, ConnexionForm, ContactForm, InscriptionForm, SimulateurForm
from ..models import AbonnementSuivi, AvisClient, Bagage, Pays, Ville, Voyage
from ..securite import limite_requetes
from ..services import ErreurMetier, calculer_prix, envoyer_courriel, notifier_admins


def accueil(request):
    pays = Pays.objects.filter(actif=True).prefetch_related("villes")
    destinations = [p for p in pays if p.code != "CA"]
    return render(request, "public/accueil.html", {
        "prochains": Voyage.reservables().order_by("depart")[:3],
        "pays_list": pays,
        "destinations": destinations,
        "nb_villes": sum(len(p.villes.all()) for p in destinations),
        "delai_min": min((p.delai_min for p in destinations), default=0),
        "avis": AvisClient.objects.filter(publie=True)[:3],
    })


def destinations(request):
    pays = Pays.objects.filter(actif=True).exclude(code="CA").prefetch_related("villes")
    filtre = request.GET.get("pays", "")
    if filtre:
        pays = pays.filter(code=filtre)
    return render(request, "public/destinations.html", {
        "pays_list": pays,
        "tous_pays": Pays.objects.filter(actif=True).exclude(code="CA"),
        "filtre": filtre,
    })


def _calcul_simulation(form):
    d = form.cleaned_data
    pays = d["pays"]
    resultat = {"pays": pays, "poids": d["poids"]}
    try:
        from ..services import poids_facture

        dims = (d.get("longueur"), d.get("largeur"), d.get("hauteur"))
        resultat["prix"] = calculer_prix(pays, d["poids"], *dims)
        resultat["poids_facture"] = poids_facture(d["poids"], *dims)
        resultat["volumetrique"] = resultat["poids_facture"] > d["poids"]
        resultat["detail_kilos"] = (resultat["poids_facture"] * pays.tarif_kg).quantize(Decimal("0.01"))
        resultat["part_fixe"] = int(pays.frais_fixes * 100 / resultat["prix"]) if resultat["prix"] else 0
    except ErreurMetier as e:
        resultat["erreur"] = str(e)
        return resultat
    voyages = Voyage.reservables().filter(ville_arrivee__pays=pays)
    if d.get("ville"):
        voyages = Voyage.filtre_ville(voyages, d["ville"])
    resultat["voyages"] = [v for v in voyages.order_by("depart")[:10] if v.kilos_restants >= d["poids"]][:5]
    if d.get("longueur") and d.get("largeur") and d.get("hauteur"):
        resultat["volume_l"] = round(d["longueur"] * d["largeur"] * d["hauteur"] / 1000, 1)
    return resultat


def simulateur(request):
    form = SimulateurForm(request.GET or None)
    form.fields["ville"].queryset = form.fields["ville"].queryset.filter(pays_id=request.GET.get("pays") or 0)
    resultat = _calcul_simulation(form) if request.GET and form.is_valid() else None
    gabarit = "public/_resultat_simulation.html" if request.headers.get("HX-Request") else "public/simulateur.html"
    return render(request, gabarit, {"form": form, "resultat": resultat})


def villes_pays(request):
    """Liste des villes d'un pays (HTMX)."""
    villes = Ville.objects.filter(pays_id=request.GET.get("pays") or 0, pays__actif=True)
    return render(request, "public/_options_villes.html", {"villes": villes, "vide": request.GET.get("vide", "Toutes les villes")})


@limite_requetes("suivi", nombre=30, secondes=60)
def suivi(request):
    numero = request.GET.get("numero", "").strip().upper()
    if numero:
        if not numero.startswith("BG-") and len(numero) == 8:
            numero = "BG-" + numero
        if Bagage.objects.filter(numero_suivi=numero, statut_paiement__in=["paye", "rembourse"]).exists():
            return redirect("suivi_detail", numero=numero)
        messages.error(request, "Aucun bagage ne correspond à ce numéro de suivi.")
    return render(request, "public/suivi_recherche.html", {"numero": numero})


@limite_requetes("suivi", nombre=30, secondes=60)
def suivi_detail(request, numero):
    bagage = get_object_or_404(
        Bagage.objects.select_related("voyage__ville_depart__pays", "voyage__ville_arrivee__pays"),
        numero_suivi=numero.upper(), statut_paiement__in=["paye", "rembourse"],
    )
    form = AbonnementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        AbonnementSuivi.objects.get_or_create(bagage=bagage, courriel=form.cleaned_data["courriel"].lower())
        messages.success(request, "Vous recevrez un courriel à chaque changement de statut.")
        return redirect("suivi_detail", numero=bagage.numero_suivi)
    return render(request, "public/suivi_detail.html", {
        "bagage": bagage, "voyage": bagage.voyage, "form": form,
        "evenements": bagage.evenements.all(),
        # Sécurité du transporteur : la page publique ne montre que le dernier lieu nommé et l'heure,
        # jamais les coordonnées. La carte détaillée est réservée au client connecté et à l'admin.
        "positions": [],
        "derniere_position": bagage.voyage.derniere_position if bagage.rang >= 2 else None,
    })


# --------------------------------------------------------------------------
# Comptes
# --------------------------------------------------------------------------


class Connexion(auth_views.LoginView):
    template_name = "comptes/connexion.html"
    authentication_form = ConnexionForm
    redirect_authenticated_user = True


def inscription(request):
    if request.user.is_authenticated:
        return redirect("redirection_role")
    form = InscriptionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        jeton = signing.dumps({"u": user.pk}, salt="confirmation-courriel")
        envoyer_courriel(
            user.email, "Confirmez votre courriel",
            f"Bonjour {user.first_name},\n\nCliquez sur ce lien pour confirmer votre courriel :",
            reverse("confirmer_courriel", args=[jeton]),
        )
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Compte créé ! Un lien de confirmation vous a été envoyé par courriel.")
        return redirect(request.GET.get("next") or "redirection_role")
    return render(request, "comptes/inscription.html", {"form": form})


def confirmer_courriel(request, jeton):
    from ..models import Utilisateur

    try:
        data = signing.loads(jeton, salt="confirmation-courriel", max_age=60 * 60 * 24 * 7)
    except signing.BadSignature:
        messages.error(request, "Lien de confirmation invalide ou expiré.")
        return redirect("accueil")
    Utilisateur.objects.filter(pk=data["u"]).update(email_confirme=True)
    messages.success(request, "Votre courriel est confirmé. Merci !")
    return redirect("redirection_role" if request.user.is_authenticated else "connexion")


@login_required
def renvoyer_confirmation(request):
    jeton = signing.dumps({"u": request.user.pk}, salt="confirmation-courriel")
    envoyer_courriel(request.user.email, "Confirmez votre courriel", "Cliquez sur ce lien pour confirmer votre courriel :",
                     reverse("confirmer_courriel", args=[jeton]))
    messages.info(request, "Un nouveau lien de confirmation vous a été envoyé.")
    return redirect(request.META.get("HTTP_REFERER") or "redirection_role")


@login_required
def redirection_role(request):
    """Redirection selon le rôle après connexion."""
    return redirect(request.user.espace_url())


class MotDePasseOublie(auth_views.PasswordResetView):
    template_name = "comptes/mdp_oublie.html"
    email_template_name = "comptes/mdp_courriel.txt"
    subject_template_name = "comptes/mdp_sujet.txt"
    success_url = reverse_lazy("mdp_envoye")


# --------------------------------------------------------------------------
# Aide
# --------------------------------------------------------------------------

FAQ = [
    ("Prix", [
        ("Comment est calculé le prix ?", "Prix = frais fixes du pays + (poids en kg × tarif par kilo). Utilisez le simulateur pour un prix exact."),
        ("Le prix peut-il changer après le paiement ?", "Non. Le prix est figé au moment du paiement, même si les tarifs changent ensuite."),
    ]),
    ("Délais", [
        ("Combien de temps prend un envoi ?", "Le délai dépend du pays (ex. 5 à 7 jours pour l'Algérie). Il est indiqué sur la page Destinations."),
        ("Jusqu'à quand puis-je déposer mon bagage ?", "Jusqu'à la date limite de dépôt du voyage, en général 24 h avant le départ."),
    ]),
    ("Objets interdits", [
        ("Que ne puis-je pas envoyer ?", "Chaque pays a sa liste d'objets interdits, visible sur la page Destinations. Les produits dangereux, inflammables ou illégaux sont toujours refusés."),
    ]),
    ("Douane", [
        ("Quels documents fournir ?", "Les documents demandés par la douane sont listés pour chaque pays sur la page Destinations."),
    ]),
    ("Remboursement", [
        ("Puis-je annuler ?", "Oui, jusqu'à la date limite de dépôt, depuis votre espace client, avec un remboursement intégral. Après le dépôt, l'annulation en ligne n'est plus possible."),
        ("Et si le voyage est annulé ?", "Vous êtes prévenu immédiatement et vous choisissez : un autre voyage ou le remboursement."),
        ("Et si mon bagage est perdu ?", "Nous lançons une recherche et vous tenons informé. S'il est déclaré perdu, la procédure de remboursement démarre."),
    ]),
]


@limite_requetes("contact", nombre=20, secondes=600)
def aide(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        msg = form.save()
        notifier_admins(f"Nouveau message de contact : {msg.sujet} ({msg.nom})", reverse("gestion_messages"), courriel=True)
        messages.success(request, "Merci ! Votre message a bien été envoyé. Nous vous répondrons rapidement.")
        return redirect("aide")
    return render(request, "public/aide.html", {"faq": FAQ, "form": form})


def conditions(request):
    return render(request, "public/conditions.html")


@require_POST
@login_required
def notifications_lues(request):
    request.user.notifications.filter(lue=False).update(lue=True)
    return redirect(request.POST.get("next") or "redirection_role")


@login_required
def notification_ouvrir(request, pk):
    n = get_object_or_404(request.user.notifications, pk=pk)
    n.lue = True
    n.save(update_fields=["lue"])
    return redirect(n.lien or "redirection_role")


@login_required
def notifications(request):
    return render(request, "public/notifications.html", {"notifications": request.user.notifications.all()[:100]})


# --------------------------------------------------------------------------
# Référencement (Google) : robots.txt et sitemap.xml
# --------------------------------------------------------------------------

PAGES_PUBLIQUES = ["accueil", "destinations", "simulateur", "suivi", "aide", "conditions", "inscription", "connexion"]


def robots_txt(request):
    from django.conf import settings
    from django.http import HttpResponse

    base = settings.SITE_URL.rstrip("/")
    lignes = ["User-agent: *", "Disallow: /client/", "Disallow: /transporteur/", "Disallow: /gestion/",
              "Disallow: /django-admin/", "Disallow: /taches/", "Disallow: /suivi/BG-", "Disallow: /api/", "", f"Sitemap: {base}/sitemap.xml"]
    return HttpResponse("\n".join(lignes) + "\n", content_type="text/plain")


def sitemap_xml(request):
    from django.conf import settings
    from django.http import HttpResponse

    base = settings.SITE_URL.rstrip("/")
    urls = "".join(f"<url><loc>{base}{reverse(n)}</loc></url>" for n in PAGES_PUBLIQUES)
    return HttpResponse('<?xml version="1.0" encoding="UTF-8"?>'
                        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
                        content_type="application/xml")


# --------------------------------------------------------------------------
# Tâches planifiées : appelée toutes les 10 min par cron-job.org (jeton secret obligatoire)
# --------------------------------------------------------------------------


def taches_verifications(request):
    import hmac

    from django.conf import settings
    from django.http import HttpResponseForbidden, JsonResponse

    from ..services import verifications_periodiques

    attendu = settings.VERIFICATIONS_JETON
    recu = request.headers.get("X-Jeton") or request.GET.get("jeton", "")
    if not attendu or not hmac.compare_digest(attendu, recu):
        return HttpResponseForbidden("Jeton invalide")
    return JsonResponse({"ok": True, **verifications_periodiques()})


# --------------------------------------------------------------------------
# Avis client (lien reçu par courriel 24 h après la livraison)
# --------------------------------------------------------------------------


def donner_avis(request, jeton):
    from django.core import signing

    from ..models import AvisClient

    try:
        donnees = signing.loads(jeton, salt="avis-client", max_age=60 * 60 * 24 * 60)
    except signing.BadSignature:
        messages.error(request, "Ce lien d'avis n'est plus valide.")
        return redirect("accueil")
    bagage = get_object_or_404(Bagage, pk=donnees["b"], statut=Bagage.Statut.LIVRE)
    if hasattr(bagage, "avis") and bagage.avis is not None:
        messages.info(request, "Merci, vous avez déjà donné votre avis pour cet envoi.")
        return redirect("accueil")
    if request.method == "POST":
        texte = (request.POST.get("texte") or "").strip()
        try:
            note = min(max(int(request.POST.get("note", 5)), 1), 5)
        except ValueError:
            note = 5
        if len(texte) < 5:
            messages.error(request, "Écrivez quelques mots sur votre expérience.")
        else:
            client = bagage.client
            nom = (request.POST.get("nom") or "").strip()[:80] or (
                f"{client.first_name} {client.last_name[:1]}." if client else "Client")
            AvisClient.objects.create(bagage=bagage, nom=nom, ville=bagage.ville_livraison.nom, note=note,
                                      texte=texte[:1000], publie=False)
            notifier_admins(f"Nouvel avis client ({note}/5) à modérer", reverse("gestion_avis"), courriel=False)
            messages.success(request, "Merci pour votre avis ! Il sera publié après vérification.")
            return redirect("accueil")
    return render(request, "public/avis.html", {"bagage": bagage})
