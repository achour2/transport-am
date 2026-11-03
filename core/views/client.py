"""Espace client (6.2) : tableau de bord, réservation en 4 étapes, paiement, détail, profil."""
import logging
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.core.files.storage import default_storage
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ..decorators import client_requis
from ..forms import (
    DestinataireForm,
    EtapeBagageForm,
    EtapeDestinataireForm,
    EtapeDestinationForm,
    ProfilForm,
)
from ..models import Bagage, DestinataireEnregistre, Paiement, Pays, Ville, Voyage
from ..pdf import recu_pdf
from ..services import (
    ErreurMetier,
    calculer_prix,
    poids_facture,
    annuler_reservation_comptoir,
    reserver_paiement_comptoir,
    annuler_envoi,
    confirmer_paiement,
    creer_bagage,
    deplacer_bagage,
    echec_paiement,
    rembourser,
    url_absolue,
    verifier_reservation,
)

log = logging.getLogger("core")
SESSION = "reservation"


@client_requis
def tableau(request):
    a_payer = request.user.bagages.filter(paiement_au_comptoir=True, statut_paiement="en_attente").exclude(
        statut="annule").select_related("voyage__ville_depart__pays", "voyage__ville_arrivee__pays")
    envois = request.user.bagages.filter(statut_paiement__in=["paye", "rembourse"]).select_related(
        "voyage__ville_depart__pays", "voyage__ville_arrivee__pays")
    return render(request, "client/tableau.html", {
        "en_cours": [b for b in envois if b.est_actif and b.statut_paiement == "paye"],
        "termines": [b for b in envois if not b.est_actif or b.statut_paiement == "rembourse"],
        "notifications": request.user.notifications.all()[:8],
        "en_attente": request.user.bagages.filter(statut_paiement__in=["en_attente", "echoue"], statut="enregistre",
                                                  paiement_au_comptoir=False)[:3] if settings.PAIEMENT_EN_LIGNE else [],
        "a_payer": a_payer,
    })


# --------------------------------------------------------------------------
# Réservation en 4 étapes (données conservées en session)
# --------------------------------------------------------------------------


def _resa(request):
    return request.session.setdefault(SESSION, {})


def _voyage_resa(request):
    vid = _resa(request).get("voyage")
    return Voyage.objects.filter(pk=vid).first() if vid else None


@client_requis
def envoi_nouveau(request, etape=1):
    resa = _resa(request)
    if etape > 1 and not resa.get("voyage"):
        return redirect("client_envoi_nouveau")
    voyage = _voyage_resa(request)
    if etape > 1 and (voyage is None or not voyage.reservations_ouvertes):
        messages.error(request, "Ce voyage n'est plus disponible. Choisissez-en un autre.")
        resa.pop("voyage", None)
        request.session.modified = True
        return redirect("client_envoi_nouveau")
    if etape > 2 and not resa.get("bagage"):
        return redirect("client_envoi_etape", etape=2)
    if etape > 3 and not resa.get("destinataire"):
        return redirect("client_envoi_etape", etape=3)

    ctx = {"etape": etape, "voyage": voyage, "resa": resa}

    if etape == 1:
        if "pays" in request.GET:
            initial = {"pays": request.GET.get("pays"), "ville": request.GET.get("ville")}
        else:
            initial = {"pays": resa.get("pays"), "ville": resa.get("ville"), "voyage": resa.get("voyage")}
        if request.GET.get("voyage"):
            v = Voyage.objects.filter(pk=request.GET["voyage"]).first()
            if v:
                initial.update(pays=v.ville_arrivee.pays_id, voyage=v.pk)
        if request.GET.get("poids"):
            resa["poids_simule"] = request.GET["poids"]
            request.session.modified = True
        form = EtapeDestinationForm(request.POST or None, initial=initial)
        if request.method == "POST" and form.is_valid():
            d = form.cleaned_data
            resa.update(pays=d["pays"].pk, ville=d["ville"].pk if d["ville"] else None, voyage=d["voyage"].pk,
                        ville_destination=(d["ville"] or d["voyage"].ville_arrivee).pk)
            request.session.modified = True
            return redirect("client_envoi_etape", etape=2)
        pays_id = form.data.get("pays") or initial.get("pays")
        voyages = Voyage.reservables().filter(ville_arrivee__pays_id=pays_id) if pays_id else Voyage.objects.none()
        ville_id = form.data.get("ville") or initial.get("ville")
        if ville_id:
            voyages = Voyage.filtre_ville(voyages, ville_id)
        form.fields["ville"].queryset = form.fields["ville"].queryset.filter(pays_id=pays_id or 0)
        form.fields["ville"].empty_label = "Toutes les villes"
        ctx.update(form=form, voyages=[v for v in voyages if not v.est_complet], pays_choisi=Pays.objects.filter(pk=pays_id or 0).first())

    elif etape == 2:
        initial = resa.get("bagage") or {}
        if not initial and resa.get("poids_simule"):
            initial = {"poids": resa["poids_simule"]}
        form = EtapeBagageForm(request.POST or None, request.FILES or None, voyage=voyage, initial=initial)
        if request.method == "POST" and form.is_valid():
            d = form.cleaned_data
            photo = d.pop("photo", None)
            donnees = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in d.items()}
            if photo:
                donnees["photo_tmp"] = default_storage.save(f"tmp/{photo.name}", photo)
            elif (resa.get("bagage") or {}).get("photo_tmp"):
                donnees["photo_tmp"] = resa["bagage"]["photo_tmp"]
            resa["bagage"] = donnees
            request.session.modified = True
            return redirect("client_envoi_etape", etape=3)
        ctx.update(form=form, pays=voyage.pays_arrivee)

    elif etape == 3:
        form = EtapeDestinataireForm(request.POST or None, client=request.user, initial=resa.get("destinataire"))
        if request.method == "POST" and form.is_valid():
            d = form.cleaned_data
            dest = {k: d.get(k, "") for k in ("dest_nom", "dest_telephone", "dest_adresse", "dest_courriel")}
            if d.get("enregistrer") and not d.get("enregistre"):
                DestinataireEnregistre.objects.get_or_create(
                    client=request.user, nom=dest["dest_nom"], telephone=dest["dest_telephone"],
                    defaults={"adresse": dest["dest_adresse"], "courriel": dest["dest_courriel"]},
                )
            resa["destinataire"] = dest
            request.session.modified = True
            return redirect("client_envoi_etape", etape=4)
        ctx.update(form=form)

    else:  # Étape 4 — récapitulatif et paiement
        b = resa["bagage"]
        pays = voyage.pays_arrivee
        poids = Decimal(b["poids"])
        ctx.update(
            ville_livraison=Ville.objects.filter(pk=resa.get("ville_destination")).first() or voyage.ville_arrivee,
            pays=pays, poids=poids, bagage=b, dest=resa["destinataire"],
            montant_kilos=(poids_facture(poids, b.get("longueur_cm"), b.get("largeur_cm"), b.get("hauteur_cm")) * pays.tarif_kg).quantize(Decimal("0.01")),
            prix=calculer_prix(pays, poids, b.get("longueur_cm"), b.get("largeur_cm"), b.get("hauteur_cm")),
            poids_facture=poids_facture(poids, b.get("longueur_cm"), b.get("largeur_cm"), b.get("hauteur_cm")),
        )
        if request.method == "POST":
            if not request.POST.get("accepte"):
                messages.error(request, "Vous devez accepter les conditions pour payer.")
                return render(request, "client/envoi_nouveau.html", ctx)
            donnees = {
                "description": b["description"], "poids": poids,
                "longueur_cm": b.get("longueur_cm"), "largeur_cm": b.get("largeur_cm"), "hauteur_cm": b.get("hauteur_cm"),
                "valeur_declaree": Decimal(b.get("valeur_declaree") or 0), **resa["destinataire"],
                "ville_destination": Ville.objects.filter(pk=resa.get("ville_destination")).first() or voyage.ville_arrivee,
            }
            try:
                if settings.PAIEMENT_EN_LIGNE:
                    bagage = creer_bagage(request.user, voyage, donnees)
                else:
                    bagage = reserver_paiement_comptoir(request.user, voyage, donnees)
            except ErreurMetier as e:
                messages.error(request, str(e))
                return redirect("client_envoi_etape", etape=1)
            if b.get("photo_tmp") and default_storage.exists(b["photo_tmp"]):
                with default_storage.open(b["photo_tmp"]) as f:
                    bagage.photo_depot.save(b["photo_tmp"].split("/")[-1], f, save=True)
                default_storage.delete(b["photo_tmp"])
            request.session.pop(SESSION, None)
            if not settings.PAIEMENT_EN_LIGNE:
                messages.success(request, f"Réservation {bagage.numero_suivi} enregistrée ! Vos kilos sont réservés : "
                                          "payez au point de dépôt avant la date limite.")
                return redirect("client_envoi", numero=bagage.numero_suivi)
            return redirect("client_payer", numero=bagage.numero_suivi)
    return render(request, "client/envoi_nouveau.html", ctx)


@client_requis
def envoi_recommencer(request):
    request.session.pop(SESSION, None)
    return redirect("client_envoi_nouveau")


# --------------------------------------------------------------------------
# Paiement (Stripe Checkout, ou paiement simulé si Stripe n'est pas configuré)
# --------------------------------------------------------------------------


def _bagage_client(request, numero):
    return get_object_or_404(Bagage.objects.select_related("voyage"), numero_suivi=numero, client=request.user)


@client_requis
def payer(request, numero):
    bagage = _bagage_client(request, numero)
    if bagage.statut_paiement == Bagage.Paiement.PAYE:
        return redirect("client_envoi", numero=numero)
    if not settings.PAIEMENT_EN_LIGNE or bagage.paiement_au_comptoir:
        messages.info(request, "Le paiement se fait au point de dépôt (espèces, carte au terminal ou virement).")
        return redirect("client_envoi", numero=numero)
    try:
        verifier_reservation(bagage.voyage, bagage.poids)
    except ErreurMetier as e:
        messages.error(request, str(e))
        return redirect("client_tableau")
    paiement = bagage.paiements.filter(statut=Paiement.Statut.EN_ATTENTE).first() or Paiement.objects.create(
        bagage=bagage, montant=bagage.prix, devise=bagage.devise)

    if settings.STRIPE_SECRET_KEY:
        import stripe

        stripe.api_key = settings.STRIPE_SECRET_KEY
        session = stripe.checkout.Session.create(
            mode="payment",
            customer_email=request.user.email,
            line_items=[{
                "quantity": 1,
                "price_data": {
                    "currency": bagage.devise.lower(),
                    "unit_amount": int(bagage.prix * 100),
                    "product_data": {"name": f"Envoi {bagage.numero_suivi} — {bagage.poids} kg vers {bagage.ville_livraison}"},
                },
            }],
            metadata={"paiement": paiement.pk},
            success_url=url_absolue(reverse("client_paiement_retour", args=[numero])) + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_absolue(reverse("client_payer", args=[numero])),
        )
        paiement.reference_stripe = session.id
        paiement.save(update_fields=["reference_stripe"])
        return redirect(session.url)

    # Mode démonstration : formulaire de carte simulé
    if request.method == "POST":
        carte = request.POST.get("carte", "").replace(" ", "")
        if carte == "4000000000000002":
            echec_paiement(paiement)
            messages.error(request, "Paiement refusé par la banque. Essayez une autre carte.")
            return redirect("client_payer", numero=numero)
        if len(carte) < 12:
            messages.error(request, "Numéro de carte invalide.")
            return redirect("client_payer", numero=numero)
        try:
            confirmer_paiement(paiement, reference=f"demo_{paiement.pk}")
        except ErreurMetier as e:
            messages.error(request, str(e))
            return redirect("client_tableau")
        messages.success(request, f"Paiement accepté ! Votre numéro de suivi : {bagage.numero_suivi}")
        return redirect("client_envoi", numero=numero)
    return render(request, "client/payer.html", {"bagage": bagage, "paiement": paiement})


@client_requis
def paiement_retour(request, numero):
    bagage = _bagage_client(request, numero)
    paiement = bagage.paiements.order_by("-cree_le").first()
    if settings.STRIPE_SECRET_KEY and paiement and paiement.statut != Paiement.Statut.PAYE:
        import stripe

        stripe.api_key = settings.STRIPE_SECRET_KEY
        session = stripe.checkout.Session.retrieve(request.GET.get("session_id", paiement.reference_stripe))
        if session.payment_status == "paid":
            try:
                confirmer_paiement(paiement, reference=session.payment_intent)
            except ErreurMetier as e:
                messages.error(request, str(e))
                return redirect("client_tableau")
    if bagage.statut_paiement == Bagage.Paiement.PAYE:
        messages.success(request, f"Paiement accepté ! Votre numéro de suivi : {bagage.numero_suivi}")
    return redirect("client_envoi", numero=numero)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    if not settings.STRIPE_SECRET_KEY:
        return HttpResponseBadRequest()
    import stripe

    try:
        event = stripe.Webhook.construct_event(request.body, request.META.get("HTTP_STRIPE_SIGNATURE", ""),
                                               settings.STRIPE_WEBHOOK_SECRET)
    except Exception:
        return HttpResponseBadRequest()
    if event["type"] == "checkout.session.completed":
        s = event["data"]["object"]
        paiement = Paiement.objects.filter(pk=s["metadata"].get("paiement")).first()
        if paiement:
            try:
                confirmer_paiement(paiement, reference=s.get("payment_intent", ""))
            except ErreurMetier:
                log.warning("Paiement %s reçu mais voyage complet : remboursement requis", paiement.pk)
    return HttpResponse(status=200)


# --------------------------------------------------------------------------
# Détail d'un envoi
# --------------------------------------------------------------------------


@client_requis
def envoi_detail(request, numero):
    bagage = _bagage_client(request, numero)
    if bagage.statut_paiement in (Bagage.Paiement.EN_ATTENTE, Bagage.Paiement.ECHOUE) and not bagage.paiement_au_comptoir:
        return redirect("client_payer", numero=numero)
    autres_voyages = []
    if bagage.choix_requis:
        autres_voyages = [v for v in Voyage.reservables().filter(ville_arrivee__pays=bagage.voyage.ville_arrivee.pays)
                          .exclude(pk=bagage.voyage_id) if v.kilos_restants >= bagage.poids]
    return render(request, "client/envoi_detail.html", {
        "bagage": bagage, "voyage": bagage.voyage, "evenements": bagage.evenements.all(),
        "positions": bagage.voyage.positions.all() if bagage.rang >= 2 else [],
        "paiement": bagage.paiements.exclude(statut=Paiement.Statut.EN_ATTENTE).first(),
        "autres_voyages": autres_voyages,
    })


@client_requis
def recu(request, numero):
    bagage = _bagage_client(request, numero)
    paiement = bagage.paiements.filter(statut__in=[Paiement.Statut.PAYE, Paiement.Statut.REMBOURSE]).first()
    if not paiement:
        messages.error(request, "Aucun reçu disponible pour cet envoi.")
        return redirect("client_envoi", numero=numero)
    reponse = HttpResponse(recu_pdf(paiement), content_type="application/pdf")
    reponse["Content-Disposition"] = f'attachment; filename="recu-{bagage.numero_suivi}.pdf"'
    return reponse


@client_requis
@require_POST
def annuler(request, numero):
    bagage = _bagage_client(request, numero)
    try:
        if bagage.a_encaisser:
            annuler_reservation_comptoir(bagage, request.user)
            messages.success(request, "Réservation annulée. Rien n'a été payé, il n'y a rien à rembourser.")
            return redirect("client_envoi", numero=numero)
        annuler_envoi(bagage, request.user)
        messages.success(request, "Envoi annulé. Le remboursement intégral est en cours.")
    except ErreurMetier as e:
        messages.error(request, str(e))
    return redirect("client_envoi", numero=numero)


@client_requis
@require_POST
def choix_voyage_annule(request, numero):
    """Voyage annulé par l'admin : le client choisit un autre voyage ou le remboursement."""
    bagage = _bagage_client(request, numero)
    if not bagage.choix_requis:
        return redirect("client_envoi", numero=numero)
    try:
        if request.POST.get("choix") == "rembourser":
            rembourser(bagage, request.user)
            from ..services import changer_statut

            changer_statut(bagage, Bagage.Statut.ANNULE, request.user, f"Envoi {bagage.numero_suivi} remboursé suite à l'annulation du voyage.")
            messages.success(request, "Remboursement effectué.")
        else:
            voyage = get_object_or_404(Voyage, pk=request.POST.get("voyage"))
            deplacer_bagage(bagage, voyage, request.user)
            messages.success(request, "Votre envoi a été déplacé sur le nouveau voyage.")
    except ErreurMetier as e:
        messages.error(request, str(e))
    return redirect("client_envoi", numero=numero)


# --------------------------------------------------------------------------
# Profil
# --------------------------------------------------------------------------


@client_requis
def profil(request):
    form = ProfilForm(request.POST or None, instance=request.user, prefix="p")
    dform = DestinataireForm(request.POST or None, prefix="d") if request.POST.get("action") == "destinataire" else DestinataireForm(prefix="d")
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "profil" and form.is_valid():
            form.save()
            from django.utils import translation

            request.session["_language"] = request.user.langue
            translation.activate(request.user.langue)
            messages.success(request, "Profil mis à jour.")
            reponse = redirect("client_profil")
            reponse.set_cookie(settings.LANGUAGE_COOKIE_NAME, request.user.langue)
            return reponse
        if action == "destinataire" and dform.is_valid():
            d = dform.save(commit=False)
            d.client = request.user
            d.save()
            messages.success(request, "Destinataire enregistré.")
            return redirect("client_profil")
        if action == "supprimer_destinataire":
            request.user.destinataires.filter(pk=request.POST.get("pk")).delete()
            return redirect("client_profil")
    return render(request, "client/profil.html", {"form": form, "dform": dform, "destinataires": request.user.destinataires.all()})


@client_requis
@require_POST
def supprimer_compte(request):
    """Droit de suppression (Loi 25) : données personnelles effacées, envois anonymisés."""
    user = request.user
    if user.bagages.filter(statut_paiement="paye").exclude(statut__in=["livre", "annule", "perdu"]).exists():
        messages.error(request, "Vous avez des envois en cours. Vous pourrez supprimer votre compte une fois ceux-ci terminés.")
        return redirect("client_profil")
    logout(request)
    user.delete()
    messages.success(request, "Votre compte et vos données personnelles ont été supprimés.")
    return redirect("accueil")
