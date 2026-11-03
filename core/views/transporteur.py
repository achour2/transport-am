"""Espace transporteur (6.3) — conçu d'abord pour le téléphone."""
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..decorators import transporteur_requis
from ..forms import IncidentForm, LivraisonForm, PositionForm
from ..models import Bagage, Voyage
from ..services import (
    ErreurMetier,
    bagages_actifs,
    demarrer_voyage,
    enregistrer_position,
    marquer_charge,
    signaler_incident,
    terminer_voyage,
    valider_livraison,
)


def _mes_voyages(request):
    return Voyage.objects.filter(transporteur=request.user).select_related("ville_depart__pays", "ville_arrivee__pays")


@transporteur_requis
def voyages(request):
    qs = _mes_voyages(request)
    return render(request, "transporteur/voyages.html", {
        "en_cours": qs.filter(statut=Voyage.Statut.EN_COURS),
        "prochains": qs.filter(statut=Voyage.Statut.PLANIFIE).order_by("depart"),
        "termines": qs.filter(statut=Voyage.Statut.TERMINE).order_by("-depart")[:10],
        "form_position": PositionForm(),
    })


@transporteur_requis
def voyage_detail(request, pk):
    voyage = get_object_or_404(_mes_voyages(request), pk=pk)
    bagages = bagages_actifs(voyage).order_by("numero_suivi")
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "charger":
                b = marquer_charge(voyage, request.POST.get("numero", ""), request.user)
                messages.success(request, f"{b.numero_suivi} marqué « chargé ».")
            elif action == "demarrer":
                demarrer_voyage(voyage, request.user)
                messages.success(request, "Voyage démarré : les bagages chargés sont « en transit ». Pensez à envoyer votre position.")
            elif action == "arrive":
                terminer_voyage(voyage, request.user)
                messages.success(request, "Voyage terminé : les bagages sont « arrivés à destination ».")
            elif action == "incident":
                form = IncidentForm(request.POST)
                if form.is_valid():
                    d = form.cleaned_data
                    bagage = None
                    if d["numero"]:
                        bagage = bagages.filter(numero_suivi=d["numero"].strip().upper()).first()
                        if not bagage:
                            raise ErreurMetier("Ce numéro ne fait pas partie du voyage.")
                    signaler_incident(voyage, request.user, d["type"], d["commentaire"], bagage)
                    messages.success(request, "Incident signalé : l'administrateur est alerté.")
        except ErreurMetier as e:
            messages.error(request, str(e))
        return redirect("transporteur_voyage", pk=pk)
    charges = bagages.filter(rang_filter()).count()
    return render(request, "transporteur/voyage_detail.html", {
        "voyage": voyage, "bagages": bagages, "charges": charges, "total": bagages.count(),
        "positions": voyage.positions.all(), "form_incident": IncidentForm(),
    })


def rang_filter():
    from django.db.models import Q

    return Q(statut__in=[Bagage.Statut.CHARGE, Bagage.Statut.EN_TRANSIT, Bagage.Statut.ARRIVE, Bagage.Statut.LIVRE, Bagage.Statut.INCIDENT])


@transporteur_requis
def position(request):
    en_cours = _mes_voyages(request).filter(statut=Voyage.Statut.EN_COURS)
    form = PositionForm(request.POST or None, initial={"voyage": en_cours.first()})
    form.fields["voyage"].queryset = en_cours
    if request.method == "POST":
        if form.is_valid():
            d = form.cleaned_data
            try:
                pos = enregistrer_position(d["voyage"], request.user, d["latitude"], d["longitude"], d["lieu"], d["commentaire"])
                from django.utils import timezone

                messages.success(request, f"Position envoyée à {timezone.localtime(pos.envoyee_le):%H:%M}. Merci !")
            except ErreurMetier as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Aucun voyage en cours.")
        return redirect(request.POST.get("next") or "transporteur_position")
    return render(request, "transporteur/position.html", {"form": form, "voyage": en_cours.first()})


@transporteur_requis
def livraison(request, numero):
    bagage = get_object_or_404(Bagage, numero_suivi=numero.upper(), voyage__transporteur=request.user)
    form = LivraisonForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            valider_livraison(bagage, form.cleaned_data["code"], form.cleaned_data.get("photo"), request.user,
                              form.cleaned_data.get("piece_4", ""))
            messages.success(request, f"Bagage {bagage.numero_suivi} livré. Le client est notifié.")
            return redirect("transporteur_voyage", pk=bagage.voyage_id)
        except ErreurMetier as e:
            messages.error(request, str(e))
    return render(request, "transporteur/livraison.html", {"bagage": bagage, "form": form})
