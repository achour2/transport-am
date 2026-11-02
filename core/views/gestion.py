"""Espace administrateur (6.4)."""
import calendar
from datetime import date, timedelta
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.forms import PasswordResetForm
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..decorators import admin_requis
from ..forms import DeplacerBagageForm, ParametresForm, PaysForm, StatutBagageForm, TransporteurForm, VoyageForm
from ..models import Bagage, Incident, MessageContact, Paiement, Parametres, Pays, Utilisateur, Voyage
from ..services import (
    ErreurMetier,
    annuler_voyage,
    changer_statut,
    deplacer_bagage,
    notifier_dates_modifiees,
    notifier_voyage_assigne,
    rembourser,
    traiter_incident,
)


def _debut_mois():
    return timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@admin_requis
def tableau(request):
    params = Parametres.charger()
    debut = _debut_mois()
    payes = Bagage.objects.filter(statut_paiement="paye", cree_le__gte=debut)
    revenus = Paiement.objects.filter(statut="paye", paye_le__gte=debut).values("devise").annotate(t=Sum("montant"))
    en_cours = Voyage.objects.filter(statut="en_cours").select_related("ville_depart", "ville_arrivee", "transporteur")
    seuil = timezone.now() - timedelta(hours=params.alerte_sans_position_heures)
    sans_position = [v for v in en_cours if (v.derniere_position.envoyee_le if v.derniere_position else v.demarre_le or timezone.now()) < seuil]
    presque_complets = [v for v in Voyage.objects.filter(statut="planifie") if v.taux_remplissage >= params.seuil_presque_complet]
    return render(request, "gestion/tableau.html", {
        "nb_envois": payes.count(),
        "revenus": revenus,
        "kilos": payes.aggregate(t=Sum("poids"))["t"] or 0,
        "en_cours": en_cours,
        "sans_position": sans_position,
        "incidents": Incident.objects.filter(etat="ouvert").select_related("bagage", "voyage")[:10],
        "presque_complets": presque_complets,
        "paiements": Paiement.objects.select_related("bagage__client").exclude(statut="en_attente")[:8],
        "reservations": Bagage.objects.filter(statut_paiement="paye").select_related("client", "voyage__ville_arrivee")[:8],
        "messages_contact": MessageContact.objects.filter(traite=False).count(),
        "notifications": request.user.notifications.filter(lue=False)[:6],
    })


@admin_requis
def export_excel(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Envois"
    entetes = ["Numéro", "Date", "Client", "Courriel", "Départ", "Arrivée", "Date départ", "Poids (kg)",
               "Prix", "Devise", "Paiement", "Statut", "Destinataire"]
    ws.append(entetes)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E79")
    qs = Bagage.objects.exclude(statut_paiement="en_attente").select_related("client", "voyage__ville_depart", "voyage__ville_arrivee")
    if request.GET.get("mois") != "tous":
        qs = qs.filter(cree_le__gte=_debut_mois())
    for b in qs:
        ws.append([
            b.numero_suivi, timezone.localtime(b.cree_le).strftime("%Y-%m-%d %H:%M"), str(b.client or ""),
            b.client.email if b.client else "", str(b.voyage.ville_depart), str(b.voyage.ville_arrivee),
            timezone.localtime(b.voyage.depart).strftime("%Y-%m-%d"), float(b.poids), float(b.prix), b.devise,
            b.get_statut_paiement_display(), b.get_statut_display(), b.dest_nom,
        ])
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 18
    tampon = BytesIO()
    wb.save(tampon)
    r = HttpResponse(tampon.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    r["Content-Disposition"] = f'attachment; filename="envois-{timezone.localdate():%Y-%m}.xlsx"'
    return r


# --------------------------------------------------------------------------
# Pays et tarifs
# --------------------------------------------------------------------------


@admin_requis
def pays_liste(request):
    pays = Pays.objects.prefetch_related("villes").annotate(
        nb_voyages=Count("villes__voyages_arrivee", distinct=True) + Count("villes__voyages_depart", distinct=True))
    return render(request, "gestion/pays_liste.html", {"pays_list": pays})


@admin_requis
def pays_form(request, pk=None):
    pays = get_object_or_404(Pays, pk=pk) if pk else None
    form = PaysForm(request.POST or None, instance=pays)
    if request.method == "POST" and form.is_valid():
        p = form.save()
        messages.success(request, f"Pays « {p.nom} » enregistré." + (" Les envois déjà payés gardent leur prix." if pk else ""))
        return redirect("gestion_pays")
    return render(request, "gestion/pays_form.html", {"form": form, "pays": pays})


@admin_requis
@require_POST
def pays_basculer(request, pk):
    pays = get_object_or_404(Pays, pk=pk)
    pays.actif = not pays.actif
    pays.save(update_fields=["actif"])
    messages.success(request, f"{pays.nom} est maintenant {'actif' if pays.actif else 'inactif'}.")
    return redirect("gestion_pays")


@admin_requis
@require_POST
def pays_supprimer(request, pk):
    pays = get_object_or_404(Pays, pk=pk)
    if pays.est_utilise():
        pays.actif = False
        pays.save(update_fields=["actif"])
        messages.warning(request, f"{pays.nom} est utilisé par des voyages : il a été désactivé au lieu d'être supprimé (l'historique est conservé).")
    else:
        pays.delete()
        messages.success(request, f"{pays.nom} supprimé.")
    return redirect("gestion_pays")


# --------------------------------------------------------------------------
# Voyages et calendrier
# --------------------------------------------------------------------------


@admin_requis
def voyages(request):
    vue = request.GET.get("vue", "liste")
    qs = Voyage.objects.select_related("ville_depart__pays", "ville_arrivee__pays", "transporteur")
    statut = request.GET.get("statut", "")
    if statut:
        qs = qs.filter(statut=statut)
    ctx = {"vue": vue, "statut": statut, "statuts": Voyage.Statut.choices}
    if vue == "calendrier":
        auj = timezone.localdate()
        annee = int(request.GET.get("annee", auj.year))
        mois = int(request.GET.get("mois", auj.month))
        semaines = calendar.Calendar(firstweekday=0).monthdatescalendar(annee, mois)
        debut, fin = semaines[0][0], semaines[-1][-1]
        par_jour = {}
        for v in qs.filter(depart__date__gte=debut - timedelta(days=1), depart__date__lte=fin + timedelta(days=1)):
            par_jour.setdefault(timezone.localtime(v.depart).date(), []).append(v)
        prec = date(annee, mois, 1) - timedelta(days=1)
        suiv = date(annee, mois, 28) + timedelta(days=5)
        ctx.update(
            semaines=[[(j, par_jour.get(j, []), j.month == mois) for j in s] for s in semaines],
            titre_mois=f"{['janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre'][mois-1]} {annee}",
            prec=prec, suiv=suiv, aujourdhui=auj,
        )
    else:
        quand = request.GET.get("quand", "a_venir")
        if quand == "a_venir":
            qs = qs.filter(depart__gte=timezone.now() - timedelta(days=1)).order_by("depart")
        else:
            qs = qs.order_by("-depart")
        ctx.update(voyages=Paginator(qs, 25).get_page(request.GET.get("page")), quand=quand)
    return render(request, "gestion/voyages.html", ctx)


@admin_requis
def voyage_form(request, pk=None, dupliquer=None):
    voyage = get_object_or_404(Voyage, pk=pk) if pk else None
    initial = {}
    if dupliquer:
        src = get_object_or_404(Voyage, pk=dupliquer)
        decal = timedelta(days=7)
        initial = {
            "ville_depart": src.ville_depart, "ville_arrivee": src.ville_arrivee,
            "depart": timezone.localtime(src.depart + decal), "arrivee_prevue": timezone.localtime(src.arrivee_prevue + decal),
            "date_limite_depot": timezone.localtime(src.date_limite_depot + decal), "lieu_depot": src.lieu_depot,
            "heure_depot": src.heure_depot, "capacite_kg": src.capacite_kg, "transporteur": src.transporteur, "moyen": src.moyen,
        }
    if voyage and voyage.statut in ("termine", "annule") and request.method == "POST":
        messages.error(request, "Un voyage terminé ou annulé ne peut plus être modifié.")
        return redirect("gestion_voyages")
    avant = None
    if voyage:
        avant = (voyage.depart, voyage.arrivee_prevue, voyage.date_limite_depot, voyage.transporteur_id)
    form = VoyageForm(request.POST or None, instance=voyage, initial=initial)
    if request.method == "POST" and form.is_valid():
        v = form.save()
        if voyage is None:
            notifier_voyage_assigne(v)
            messages.success(request, "Voyage créé." + (" Le transporteur est notifié." if v.transporteur else ""))
        else:
            if avant[:3] != (v.depart, v.arrivee_prevue, v.date_limite_depot):
                notifier_dates_modifiees(v)
                messages.info(request, "Dates modifiées : les clients et le transporteur ont été notifiés.")
            if avant[3] != v.transporteur_id:
                notifier_voyage_assigne(v)
            messages.success(request, "Voyage enregistré.")
        return redirect("gestion_voyages")
    bagages = voyage.bagages.filter(statut_paiement="paye").select_related("client") if voyage else []
    return render(request, "gestion/voyage_form.html", {"form": form, "voyage": voyage, "bagages": bagages, "duplique": dupliquer})


@admin_requis
@require_POST
def voyage_annuler(request, pk):
    voyage = get_object_or_404(Voyage, pk=pk)
    try:
        annuler_voyage(voyage, request.user)
        messages.success(request, "Voyage annulé. Chaque client est notifié et peut choisir un autre voyage ou le remboursement.")
    except ErreurMetier as e:
        messages.error(request, str(e))
    return redirect("gestion_voyages")


# --------------------------------------------------------------------------
# Bagages
# --------------------------------------------------------------------------


@admin_requis
def bagages(request):
    qs = Bagage.objects.exclude(statut_paiement="en_attente").select_related(
        "client", "voyage__ville_depart", "voyage__ville_arrivee__pays")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(numero_suivi__icontains=q) | Q(client__first_name__icontains=q) | Q(client__last_name__icontains=q)
                       | Q(client__email__icontains=q) | Q(dest_nom__icontains=q))
    f = {k: request.GET.get(k, "") for k in ("statut", "voyage", "pays", "date")}
    if f["statut"]:
        qs = qs.filter(statut=f["statut"])
    if f["voyage"]:
        qs = qs.filter(voyage_id=f["voyage"])
    if f["pays"]:
        qs = qs.filter(voyage__ville_arrivee__pays_id=f["pays"])
    if f["date"]:
        qs = qs.filter(cree_le__date=f["date"])
    return render(request, "gestion/bagages.html", {
        "bagages": Paginator(qs, 30).get_page(request.GET.get("page")), "q": q, "f": f,
        "statuts": Bagage.Statut.choices, "pays_list": Pays.objects.all(),
        "voyages_list": Voyage.objects.exclude(statut="annule").select_related("ville_depart", "ville_arrivee").order_by("-depart")[:50],
    })


@admin_requis
def bagage_detail(request, numero):
    bagage = get_object_or_404(Bagage, numero_suivi=numero)
    sform = StatutBagageForm(initial={"statut": bagage.statut})
    dform = DeplacerBagageForm(bagage=bagage)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "statut":
                sform = StatutBagageForm(request.POST)
                if sform.is_valid():
                    changer_statut(bagage, sform.cleaned_data["statut"], request.user, sform.cleaned_data["message"] or None)
                    messages.success(request, "Statut mis à jour, client notifié.")
            elif action == "deplacer":
                dform = DeplacerBagageForm(request.POST, bagage=bagage)
                if dform.is_valid():
                    deplacer_bagage(bagage, dform.cleaned_data["voyage"], request.user)
                    messages.success(request, "Bagage déplacé.")
            elif action == "rembourser":
                rembourser(bagage, request.user)
                if bagage.statut == Bagage.Statut.ENREGISTRE or bagage.choix_requis:
                    changer_statut(bagage, Bagage.Statut.ANNULE, request.user, f"Envoi {bagage.numero_suivi} annulé et remboursé.")
                messages.success(request, "Remboursement effectué.")
            elif action == "incident":
                from ..services import signaler_incident

                signaler_incident(bagage.voyage, request.user, request.POST.get("type", "autre"), request.POST.get("commentaire", ""), bagage)
                messages.success(request, "Incident ouvert.")
        except ErreurMetier as e:
            messages.error(request, str(e))
        return redirect("gestion_bagage", numero=numero)
    return render(request, "gestion/bagage_detail.html", {
        "bagage": bagage, "sform": sform, "dform": dform, "evenements": bagage.evenements.select_related("auteur"),
        "paiements": bagage.paiements.all(), "incidents": bagage.incidents.all(), "types_incident": Incident.Type.choices,
    })


@admin_requis
def incidents(request):
    if request.method == "POST":
        inc = get_object_or_404(Incident, pk=request.POST.get("pk"))
        try:
            traiter_incident(inc, request.POST.get("etat"), request.user)
            messages.success(request, "Incident mis à jour, client informé.")
        except ErreurMetier as e:
            messages.error(request, str(e))
        return redirect("gestion_incidents")
    return render(request, "gestion/incidents.html", {
        "ouverts": Incident.objects.filter(etat="ouvert").select_related("bagage", "voyage", "signale_par"),
        "traites": Incident.objects.exclude(etat="ouvert").select_related("bagage", "voyage")[:30],
    })


# --------------------------------------------------------------------------
# Utilisateurs, messages, paramètres
# --------------------------------------------------------------------------


@admin_requis
def utilisateurs(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "creer":
            form = TransporteurForm(request.POST)
            if form.is_valid():
                t = form.save()
                messages.success(request, f"Compte transporteur créé pour {t}.")
                return redirect("gestion_utilisateurs")
        else:
            u = get_object_or_404(Utilisateur, pk=request.POST.get("pk"))
            if u == request.user:
                messages.error(request, "Vous ne pouvez pas modifier votre propre compte ici.")
            elif action == "bloquer":
                u.is_active = not u.is_active
                u.save(update_fields=["is_active"])
                messages.success(request, f"Compte de {u} {'débloqué' if u.is_active else 'bloqué'}.")
            elif action == "reinitialiser":
                f = PasswordResetForm({"email": u.email})
                if f.is_valid():
                    f.save(request=request, use_https=request.is_secure(), email_template_name="comptes/mdp_courriel.txt",
                           subject_template_name="comptes/mdp_sujet.txt")
                messages.success(request, f"Lien de réinitialisation envoyé à {u.email}.")
            return redirect("gestion_utilisateurs")
    else:
        form = TransporteurForm()
    q = request.GET.get("q", "")
    clients = Utilisateur.objects.filter(role="client").annotate(nb=Count("bagages", filter=Q(bagages__statut_paiement="paye")))
    if q:
        clients = clients.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    return render(request, "gestion/utilisateurs.html", {
        "form": form, "q": q,
        "clients": Paginator(clients.order_by("-date_joined"), 30).get_page(request.GET.get("page")),
        "transporteurs": Utilisateur.objects.filter(role="transporteur").annotate(nb=Count("voyages")),
    })


@admin_requis
def messages_contact(request):
    if request.method == "POST":
        MessageContact.objects.filter(pk=request.POST.get("pk")).update(traite=True)
        return redirect("gestion_messages")
    return render(request, "gestion/messages.html", {"liste": MessageContact.objects.all()[:100]})


@admin_requis
def parametres(request):
    form = ParametresForm(request.POST or None, instance=Parametres.charger())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Paramètres enregistrés.")
        return redirect("gestion_parametres")
    return render(request, "gestion/parametres.html", {"form": form})
