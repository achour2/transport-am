"""
Règles de gestion (section 5) et notifications (section 8).
Toute modification d'état passe par ces fonctions pour garantir
l'historique, les notifications et la cohérence des capacités.
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import (
    AbonnementSuivi,
    Bagage,
    EvenementBagage,
    Incident,
    Notification,
    Paiement,
    Parametres,
    Utilisateur,
    Voyage,
)

log = logging.getLogger("core")


class ErreurMetier(Exception):
    """Règle de gestion non respectée (message affichable à l'utilisateur)."""


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------


def url_absolue(chemin):
    return settings.SITE_URL.rstrip("/") + chemin


def envoyer_courriel(destinataire, sujet, message, lien=""):
    nom = Parametres.charger().nom_entreprise
    corps = message + (f"\n\n{url_absolue(lien)}" if lien else "") + f"\n\n— L'équipe {nom}"
    try:
        send_mail(f"[{nom}] {sujet}", corps, None, [destinataire], fail_silently=False)
    except Exception:  # un courriel en échec ne doit jamais bloquer l'action
        log.exception("Échec d'envoi du courriel à %s", destinataire)


def envoyer_sms(telephone, message):
    """Envoi SMS : prévu en version 2 (fournisseur à choisir). Journalisé en V1."""
    log.info("SMS → %s : %s", telephone, message)


def notifier(utilisateur, message, lien="", sujet=None, courriel=True):
    """Notification dans le site + courriel selon les préférences de l'utilisateur."""
    if utilisateur is None or not utilisateur.is_active:
        return None
    notif = Notification.objects.create(destinataire=utilisateur, message=message[:255], lien=lien)
    if courriel and utilisateur.notif_courriel:
        envoyer_courriel(utilisateur.email, sujet or message[:80], message, lien)
    if utilisateur.notif_sms and utilisateur.telephone:
        envoyer_sms(utilisateur.telephone, message)
    return notif


def notifier_admins(message, lien="", courriel=True):
    for admin in Utilisateur.objects.filter(role=Utilisateur.Role.ADMIN, is_active=True):
        notifier(admin, message, lien, courriel=courriel)


def notifier_abonnes(bagage, message):
    lien = reverse("suivi_detail", args=[bagage.numero_suivi])
    for abo in AbonnementSuivi.objects.filter(bagage=bagage):
        envoyer_courriel(abo.courriel, f"Suivi {bagage.numero_suivi}", message, lien)


# --------------------------------------------------------------------------
# Prix
# --------------------------------------------------------------------------


def poids_facture(poids, longueur=None, largeur=None, hauteur=None):
    """Poids facturé = max(poids réel, L×l×H ÷ diviseur) si le poids volumétrique est activé (Paramètres)."""
    poids = Decimal(str(poids))
    diviseur = Parametres.charger().diviseur_volumetrique
    if diviseur and longueur and largeur and hauteur:
        volumetrique = (Decimal(longueur) * Decimal(largeur) * Decimal(hauteur) / Decimal(diviseur)).quantize(Decimal("0.01"))
        return max(poids, volumetrique)
    return poids


def calculer_prix(pays, poids, longueur=None, largeur=None, hauteur=None):
    """Prix = frais fixes du pays + (poids facturé × tarif par kilo). Refusé au-delà du poids max (poids réel)."""
    poids = Decimal(str(poids))
    if poids <= 0:
        raise ErreurMetier("Le poids doit être supérieur à 0.")
    if poids > pays.poids_max:
        raise ErreurMetier(f"Le poids dépasse le maximum autorisé pour {pays.nom} ({pays.poids_max} kg).")
    return pays.calculer_prix(poids_facture(poids, longueur, largeur, hauteur))


# --------------------------------------------------------------------------
# Statuts des bagages
# --------------------------------------------------------------------------

MESSAGES_STATUT = {
    Bagage.Statut.ENREGISTRE: "Votre envoi {n} est enregistré.",
    Bagage.Statut.DEPOSE: "Votre bagage {n} a été déposé au point de dépôt.",
    Bagage.Statut.CHARGE: "Votre bagage {n} a été chargé.",
    Bagage.Statut.EN_TRANSIT: "Votre bagage {n} est en transit.",
    Bagage.Statut.ARRIVE: "Votre bagage {n} est arrivé à destination.",
    Bagage.Statut.LIVRE: "Votre bagage {n} a été livré au destinataire.",
    Bagage.Statut.INCIDENT: "Un incident concerne votre bagage {n} : une recherche est en cours.",
    Bagage.Statut.PERDU: "Votre bagage {n} est déclaré perdu. La procédure de remboursement est lancée.",
    Bagage.Statut.ANNULE: "Votre envoi {n} est annulé.",
}


def changer_statut(bagage, statut, auteur=None, message=None, notifier_client=True):
    bagage.statut = statut
    bagage.save(update_fields=["statut"])
    texte = message or MESSAGES_STATUT.get(statut, "Statut mis à jour").format(n=bagage.numero_suivi)
    EvenementBagage.objects.create(bagage=bagage, statut=statut, message=texte, auteur=auteur)
    if notifier_client:
        if bagage.client:
            notifier(bagage.client, texte, reverse("client_envoi", args=[bagage.numero_suivi]), sujet=f"Envoi {bagage.numero_suivi}")
        notifier_abonnes(bagage, texte)
    return bagage


# --------------------------------------------------------------------------
# Réservation et paiement
# --------------------------------------------------------------------------


def verifier_reservation(voyage, poids, bagage_exclu=None):
    if not voyage.reservations_ouvertes:
        raise ErreurMetier("Les réservations sont fermées pour ce voyage.")
    pays = voyage.pays_arrivee
    calculer_prix(pays, poids)
    restants = voyage.kilos_restants
    if bagage_exclu is not None and bagage_exclu.voyage_id == voyage.pk and bagage_exclu.statut_paiement == Bagage.Paiement.PAYE:
        restants += bagage_exclu.poids
    if Decimal(str(poids)) > restants:
        raise ErreurMetier(f"Capacité insuffisante : il reste {restants} kg sur ce voyage.")


def creer_bagage(client, voyage, donnees):
    """Crée un envoi en attente de paiement avec un prix figé."""
    verifier_reservation(voyage, donnees["poids"])
    donnees = dict(donnees)
    ville = donnees.get("ville_destination") or voyage.ville_arrivee
    if not voyage.dessert(ville):
        raise ErreurMetier(f"Ce voyage ne dessert pas {ville.nom}.")
    donnees["ville_destination"] = ville
    pays = voyage.pays_arrivee
    pf = poids_facture(donnees["poids"], donnees.get("longueur_cm"), donnees.get("largeur_cm"), donnees.get("hauteur_cm"))
    donnees.setdefault("declaration_contenu_le", timezone.now())
    bagage = Bagage.objects.create(
        client=client,
        voyage=voyage,
        frais_fixes=pays.frais_fixes,
        tarif_kg=pays.tarif_kg,
        poids_facture=pf,
        prix=pays.calculer_prix(pf),
        devise=pays.devise,
        **donnees,
    )
    return bagage


@transaction.atomic
def confirmer_paiement(paiement, reference=""):
    """Paiement accepté : capacité vérifiée et mise à jour, numéro de suivi, reçu, code de remise."""
    paiement = Paiement.objects.select_for_update().get(pk=paiement.pk)
    if paiement.statut == Paiement.Statut.PAYE:
        return paiement
    bagage = paiement.bagage
    voyage = Voyage.objects.select_for_update().get(pk=bagage.voyage_id)
    restants = voyage.kilos_restants
    if bagage.a_encaisser and timezone.now() < voyage.date_limite_depot:
        restants += bagage.poids  # ses kilos sont déjà comptés comme réservés
    if bagage.poids > restants:
        if bagage.paiement_au_comptoir:
            paiement.delete()
            raise ErreurMetier(f"Capacité insuffisante : il ne reste que {restants} kg sur ce voyage. "
                               "Déplacez l'envoi vers un autre voyage avant d'encaisser.")
        paiement.statut = Paiement.Statut.ECHOUE
        paiement.save()
        bagage.statut_paiement = Bagage.Paiement.ECHOUE
        bagage.save(update_fields=["statut_paiement"])
        raise ErreurMetier("Le voyage est devenu complet pendant le paiement. Vous ne serez pas débité.")

    paiement.statut = Paiement.Statut.PAYE
    paiement.paye_le = timezone.now()
    if reference:
        paiement.reference_stripe = reference
    paiement.save()
    bagage.statut_paiement = Bagage.Paiement.PAYE
    bagage.save(update_fields=["statut_paiement"])
    EvenementBagage.objects.create(
        bagage=bagage, statut=Bagage.Statut.ENREGISTRE, message="Envoi enregistré et payé.", auteur=bagage.client
    )

    params = Parametres.charger()
    tz_dep = voyage.pays_depart.fuseau
    from zoneinfo import ZoneInfo

    limite = timezone.localtime(voyage.date_limite_depot, ZoneInfo(tz_dep))
    lien = reverse("client_envoi", args=[bagage.numero_suivi])
    if bagage.client:
        message = (
            f"{params.texte_courriel_confirmation}\n\n"
            f"Numéro de suivi : {bagage.numero_suivi}\n"
            f"Montant payé : {paiement.montant} {paiement.devise} (reçu {paiement.numero_recu})\n"
            f"Lieu de dépôt : {voyage.lieu_depot}\n"
            f"Date limite de dépôt : {limite:%d/%m/%Y à %H:%M}\n"
            f"Code de remise (à transmettre au destinataire) : {bagage.code_remise}\n\n"
            f"Conditions générales applicables à cet envoi : {url_absolue(reverse('conditions'))}\n"
            + (f"{params.nom_legal} — NEQ {params.neq} — {params.adresse_legale}" if params.nom_legal else params.nom_entreprise)
        )
        Notification.objects.create(
            destinataire=bagage.client, message=f"Réservation confirmée : {bagage.numero_suivi}", lien=lien
        )
        envoyer_courriel(bagage.client.email, f"Réservation confirmée {bagage.numero_suivi}", message, lien)
    # Destinataire : SMS avec le code de remise (+ courriel s'il est connu)
    texte_dest = (
        f"Un bagage vous est envoyé ({bagage.numero_suivi}). Code de remise : {bagage.code_remise}. "
        f"Suivi : {url_absolue(reverse('suivi_detail', args=[bagage.numero_suivi]))}"
    )
    envoyer_sms(bagage.dest_telephone, texte_dest)
    if bagage.dest_courriel:
        envoyer_courriel(bagage.dest_courriel, "Un bagage vous est envoyé", texte_dest)

    # Voyage presque complet (90 %)
    if not voyage.alerte_presque_complet and voyage.taux_remplissage >= params.seuil_presque_complet:
        voyage.alerte_presque_complet = True
        voyage.save(update_fields=["alerte_presque_complet"])
        notifier_admins(
            f"Voyage presque complet ({voyage.taux_remplissage} %) : {voyage}",
            reverse("gestion_voyage_modifier", args=[voyage.pk]),
            courriel=False,
        )
    return paiement


def echec_paiement(paiement):
    paiement.statut = Paiement.Statut.ECHOUE
    paiement.save()
    paiement.bagage.statut_paiement = Bagage.Paiement.ECHOUE
    paiement.bagage.save(update_fields=["statut_paiement"])


def rembourser(bagage, auteur=None):
    """Remboursement intégral (via Stripe si configuré) et libération des kilos."""
    paiement = bagage.paiements.filter(statut=Paiement.Statut.PAYE).first()
    if paiement is None:
        raise ErreurMetier("Aucun paiement à rembourser pour cet envoi.")
    if paiement.mode == Paiement.Mode.CARTE and settings.STRIPE_SECRET_KEY and paiement.reference_stripe.startswith(("pi_", "ch_")):
        import stripe

        stripe.api_key = settings.STRIPE_SECRET_KEY
        stripe.Refund.create(payment_intent=paiement.reference_stripe)
    paiement.statut = Paiement.Statut.REMBOURSE
    paiement.rembourse_le = timezone.now()
    paiement.save()
    bagage.statut_paiement = Bagage.Paiement.REMBOURSE
    bagage.choix_requis = False
    bagage.save(update_fields=["statut_paiement", "choix_requis"])
    texte = f"Remboursement de {paiement.montant} {paiement.devise}"
    if paiement.mode != Paiement.Mode.CARTE:
        texte += f" à effectuer au comptoir ({paiement.get_mode_display().lower()})"
        notifier_admins(f"Remboursement à rendre en main propre : {bagage.numero_suivi} ({paiement.montant} {paiement.devise})",
                        reverse("gestion_bagage", args=[bagage.numero_suivi]), courriel=False)
    EvenementBagage.objects.create(bagage=bagage, statut=bagage.statut, message=texte + ".", auteur=auteur)
    return paiement


@transaction.atomic
def annuler_envoi(bagage, auteur):
    """Annulation par le client : possible jusqu'à la date limite de dépôt."""
    if not bagage.annulable:
        raise ErreurMetier("Annulation impossible en ligne après la date limite de dépôt ou le dépôt du bagage.")
    rembourser(bagage, auteur)
    changer_statut(bagage, Bagage.Statut.ANNULE, auteur, f"Envoi {bagage.numero_suivi} annulé et remboursé intégralement.")


@transaction.atomic
def deplacer_bagage(bagage, nouveau_voyage, auteur):
    """Déplace un envoi vers un autre voyage vers le même pays (prix inchangé)."""
    if nouveau_voyage.pk == bagage.voyage_id:
        raise ErreurMetier("Le bagage est déjà sur ce voyage.")
    if nouveau_voyage.ville_arrivee.pays_id != bagage.voyage.ville_arrivee.pays_id:
        raise ErreurMetier("Le nouveau voyage doit aller vers le même pays.")
    nouveau = Voyage.objects.select_for_update().get(pk=nouveau_voyage.pk)
    if nouveau.statut != Voyage.Statut.PLANIFIE:
        raise ErreurMetier("Le nouveau voyage doit être planifié.")
    if bagage.poids > nouveau.kilos_restants:
        raise ErreurMetier(f"Capacité insuffisante sur ce voyage ({nouveau.kilos_restants} kg restants).")
    bagage.voyage = nouveau
    bagage.choix_requis = False
    if not nouveau.dessert(bagage.ville_livraison):
        bagage.ville_destination = nouveau.ville_arrivee
    bagage.save(update_fields=["voyage", "choix_requis", "ville_destination"])
    changer_statut(bagage, bagage.statut if bagage.statut != Bagage.Statut.ANNULE else Bagage.Statut.ENREGISTRE,
                   auteur, f"Envoi {bagage.numero_suivi} déplacé sur le voyage du {timezone.localtime(nouveau.depart):%d/%m/%Y}.")


# --------------------------------------------------------------------------
# Voyages
# --------------------------------------------------------------------------


def notifier_voyage_assigne(voyage):
    if voyage.transporteur:
        notifier(voyage.transporteur, f"Nouveau voyage assigné : {voyage}", reverse("transporteur_voyage", args=[voyage.pk]))


def notifier_dates_modifiees(voyage):
    message = (
        f"Les dates du voyage {voyage.ville_depart.nom} → {voyage.destinations_texte} ont changé : "
        f"départ le {timezone.localtime(voyage.depart):%d/%m/%Y %H:%M}, "
        f"dépôt avant le {timezone.localtime(voyage.date_limite_depot):%d/%m/%Y %H:%M}."
    )
    for b in voyage.bagages.filter(statut_paiement=Bagage.Paiement.PAYE).exclude(statut=Bagage.Statut.ANNULE):
        if b.client:
            notifier(b.client, message, reverse("client_envoi", args=[b.numero_suivi]))
    if voyage.transporteur:
        notifier(voyage.transporteur, message, reverse("transporteur_voyage", args=[voyage.pk]))


@transaction.atomic
def annuler_voyage(voyage, auteur):
    if voyage.statut != Voyage.Statut.PLANIFIE:
        raise ErreurMetier("Seul un voyage planifié peut être annulé.")
    voyage.statut = Voyage.Statut.ANNULE
    voyage.save(update_fields=["statut"])
    for b in voyage.bagages.filter(statut_paiement=Bagage.Paiement.PAYE).exclude(statut=Bagage.Statut.ANNULE):
        b.choix_requis = True
        b.save(update_fields=["choix_requis"])
        EvenementBagage.objects.create(bagage=b, statut=b.statut, message="Voyage annulé par l'entreprise.", auteur=auteur)
        if b.client:
            notifier(
                b.client,
                f"Le voyage de votre envoi {b.numero_suivi} est annulé. Choisissez un autre voyage ou le remboursement.",
                reverse("client_envoi", args=[b.numero_suivi]),
            )
    if voyage.transporteur:
        notifier(voyage.transporteur, f"Voyage annulé : {voyage}", reverse("transporteur_voyages"))


@transaction.atomic
def marquer_charge(voyage, numero, auteur):
    numero = numero.strip().upper()
    try:
        bagage = voyage.bagages.get(numero_suivi=numero)
    except Bagage.DoesNotExist:
        raise ErreurMetier(f"Le bagage {numero} n'appartient pas à ce voyage.")
    if bagage.statut_paiement != Bagage.Paiement.PAYE or bagage.statut == Bagage.Statut.ANNULE:
        raise ErreurMetier(f"Le bagage {numero} n'est pas payé ou est annulé.")
    if bagage.statut == Bagage.Statut.CHARGE:
        raise ErreurMetier(f"Le bagage {numero} est déjà chargé.")
    if bagage.statut not in (Bagage.Statut.ENREGISTRE, Bagage.Statut.DEPOSE):
        raise ErreurMetier(f"Le bagage {numero} ne peut pas être chargé (statut : {bagage.get_statut_display()}).")
    return changer_statut(bagage, Bagage.Statut.CHARGE, auteur)


def bagages_actifs(voyage):
    return voyage.bagages.filter(statut_paiement=Bagage.Paiement.PAYE).exclude(
        statut__in=[Bagage.Statut.ANNULE]
    )


@transaction.atomic
def demarrer_voyage(voyage, auteur):
    if voyage.statut != Voyage.Statut.PLANIFIE:
        raise ErreurMetier("Ce voyage n'est pas au statut planifié.")
    voyage.statut = Voyage.Statut.EN_COURS
    voyage.demarre_le = timezone.now()
    voyage.dernier_rappel_position = timezone.now()
    voyage.save(update_fields=["statut", "demarre_le", "dernier_rappel_position"])
    for b in bagages_actifs(voyage).filter(statut=Bagage.Statut.CHARGE):
        changer_statut(b, Bagage.Statut.EN_TRANSIT, auteur)


@transaction.atomic
def terminer_voyage(voyage, auteur):
    if voyage.statut != Voyage.Statut.EN_COURS:
        raise ErreurMetier("Ce voyage n'est pas en cours.")
    voyage.statut = Voyage.Statut.TERMINE
    voyage.termine_le = timezone.now()
    voyage.save(update_fields=["statut", "termine_le"])
    for b in bagages_actifs(voyage).filter(statut=Bagage.Statut.EN_TRANSIT):
        changer_statut(b, Bagage.Statut.ARRIVE, auteur)


def enregistrer_position(voyage, auteur, latitude=None, longitude=None, lieu="", commentaire=""):
    from .models import Position

    if voyage.statut != Voyage.Statut.EN_COURS:
        raise ErreurMetier("La position ne peut être envoyée que pour un voyage en cours.")
    if latitude is None and not lieu:
        raise ErreurMetier("Indiquez la position GPS ou le nom du lieu.")
    if latitude is None and lieu:
        # Saisie manuelle : on reprend les coordonnées d'une ville connue si le nom correspond
        from .models import Ville

        ville = Ville.objects.filter(nom__iexact=lieu.split(",")[0].strip()).first()
        if ville and ville.latitude is not None:
            latitude, longitude = ville.latitude, ville.longitude
    return Position.objects.create(
        voyage=voyage, latitude=latitude, longitude=longitude, lieu=lieu, commentaire=commentaire, transporteur=auteur
    )


ESSAIS_CODE_MAX = 5


def valider_livraison(bagage, code, photo, auteur, piece_4=""):
    """Remise : bon code obligatoire. Après 5 codes faux, la remise est bloquée jusqu'au déblocage par l'admin."""
    import hmac

    if bagage.statut != Bagage.Statut.ARRIVE:
        raise ErreurMetier("Le bagage doit être « arrivé à destination » pour être livré.")
    if bagage.remise_bloquee:
        raise ErreurMetier("Remise bloquée après trop de codes faux. L'administrateur doit la débloquer.")
    if not hmac.compare_digest(code.strip(), bagage.code_remise):
        bagage.essais_code += 1
        champs = ["essais_code"]
        if bagage.essais_code >= ESSAIS_CODE_MAX:
            bagage.remise_bloquee = True
            champs.append("remise_bloquee")
        bagage.save(update_fields=champs)
        if bagage.remise_bloquee:
            EvenementBagage.objects.create(bagage=bagage, statut=bagage.statut, auteur=auteur,
                                           message=f"Remise bloquée : {ESSAIS_CODE_MAX} codes faux.")
            notifier_admins(f"Remise bloquée ({ESSAIS_CODE_MAX} codes faux) pour {bagage.numero_suivi}",
                            reverse("gestion_bagage", args=[bagage.numero_suivi]))
            raise ErreurMetier("Code incorrect. Remise bloquée : l'administrateur a été alerté.")
        reste = ESSAIS_CODE_MAX - bagage.essais_code
        raise ErreurMetier(f"Code de remise incorrect. Encore {reste} essai{'s' if reste > 1 else ''}.")
    bagage.photo_livraison = photo or bagage.photo_livraison
    bagage.dest_piece_4 = (piece_4 or "").strip()[:4]
    bagage.essais_code = 0
    bagage.save(update_fields=["photo_livraison", "dest_piece_4", "essais_code"])
    return changer_statut(bagage, Bagage.Statut.LIVRE, auteur)


def debloquer_remise(bagage, admin):
    bagage.remise_bloquee = False
    bagage.essais_code = 0
    bagage.save(update_fields=["remise_bloquee", "essais_code"])
    EvenementBagage.objects.create(bagage=bagage, statut=bagage.statut, auteur=admin, message="Remise débloquée par l'administrateur.")


# --------------------------------------------------------------------------
# Incidents
# --------------------------------------------------------------------------


@transaction.atomic
def signaler_incident(voyage, auteur, type_incident, commentaire="", bagage=None):
    incident = Incident.objects.create(
        voyage=voyage, bagage=bagage, type=type_incident, commentaire=commentaire, signale_par=auteur,
        statut_avant=bagage.statut if bagage else "",
    )
    libelle = incident.get_type_display()
    cible = f"bagage {bagage.numero_suivi}" if bagage else f"voyage {voyage}"
    notifier_admins(f"Incident signalé ({libelle}) — {cible}", reverse("gestion_incidents"))
    if bagage:
        if type_incident in (Incident.Type.INTROUVABLE, Incident.Type.ENDOMMAGE):
            changer_statut(bagage, Bagage.Statut.INCIDENT, auteur,
                           f"Incident sur votre bagage {bagage.numero_suivi} ({libelle.lower()}) : une recherche est en cours.")
        else:
            EvenementBagage.objects.create(bagage=bagage, statut=bagage.statut, message=f"Incident : {libelle}.", auteur=auteur)
            if bagage.client:
                notifier(bagage.client, f"Incident sur votre bagage {bagage.numero_suivi} : {libelle}.",
                         reverse("client_envoi", args=[bagage.numero_suivi]))
    else:
        for b in bagages_actifs(voyage):
            if b.client:
                notifier(b.client, f"Incident sur le voyage de votre bagage {b.numero_suivi} : {libelle}.",
                         reverse("client_envoi", args=[b.numero_suivi]))
    return incident


@transaction.atomic
def traiter_incident(incident, etat, auteur):
    incident.etat = etat
    incident.traite_le = timezone.now()
    incident.save()
    b = incident.bagage
    if not b:
        return incident
    if etat == Incident.Etat.RETROUVE:
        reprise = incident.statut_avant or Bagage.Statut.EN_TRANSIT
        if reprise == Bagage.Statut.INCIDENT:
            reprise = Bagage.Statut.EN_TRANSIT
        changer_statut(b, reprise, auteur, f"Bagage {b.numero_suivi} retrouvé : le suivi reprend.")
    elif etat == Incident.Etat.PERDU:
        changer_statut(b, Bagage.Statut.PERDU, auteur)
        if b.statut_paiement == Bagage.Paiement.PAYE:
            rembourser(b, auteur)
        if b.indemnite_suggeree:
            EvenementBagage.objects.create(
                bagage=b, statut=b.statut, auteur=auteur,
                message=f"Indemnité prévue par les conditions : {b.indemnite_suggeree} {b.devise} "
                        f"(valeur déclarée {b.valeur_declaree}, plafonnée) — à verser au client.")
            notifier_admins(f"Indemnité à verser pour {b.numero_suivi} : {b.indemnite_suggeree} {b.devise}",
                            reverse("gestion_bagage", args=[b.numero_suivi]), courriel=False)
    elif etat == Incident.Etat.RESOLU and b.statut == Bagage.Statut.INCIDENT:
        changer_statut(b, incident.statut_avant or Bagage.Statut.EN_TRANSIT, auteur, f"Incident résolu pour {b.numero_suivi}.")
    return incident


# --------------------------------------------------------------------------
# Tâches planifiées (rappels et alertes)
# --------------------------------------------------------------------------


def verifications_periodiques(maintenant=None):
    """Rappels de position (2 h), alertes sans position (4 h), rappels de date limite (24 h)."""
    maintenant = maintenant or timezone.now()
    params = Parametres.charger()
    rappel = timezone.timedelta(hours=params.rappel_position_heures)
    alerte = timezone.timedelta(hours=params.alerte_sans_position_heures)
    resultat = {"rappels": 0, "alertes": 0, "rappels_depot": 0}

    for voyage in Voyage.objects.filter(statut=Voyage.Statut.EN_COURS).select_related("transporteur"):
        derniere = voyage.derniere_position
        ref_position = derniere.envoyee_le if derniere else voyage.demarre_le or maintenant
        ref_rappel = max(ref_position, voyage.dernier_rappel_position or ref_position)
        if maintenant - ref_rappel >= rappel:
            notifier(voyage.transporteur, "Merci de mettre à jour votre position.", reverse("transporteur_position"))
            voyage.dernier_rappel_position = maintenant
            voyage.save(update_fields=["dernier_rappel_position"])
            resultat["rappels"] += 1
        if maintenant - ref_position >= alerte:
            deja = voyage.derniere_alerte_admin and voyage.derniere_alerte_admin >= ref_position
            if not deja:
                heures = int((maintenant - ref_position).total_seconds() // 3600)
                notifier_admins(f"Aucune position depuis {heures} h pour le voyage {voyage}.",
                                reverse("gestion_tableau"))
                voyage.derniere_alerte_admin = maintenant
                voyage.save(update_fields=["derniere_alerte_admin"])
                resultat["alertes"] += 1

    expirees = Bagage.objects.filter(
        paiement_au_comptoir=True, statut_paiement=Bagage.Paiement.EN_ATTENTE,
        voyage__date_limite_depot__lte=maintenant,
    ).exclude(statut=Bagage.Statut.ANNULE)
    for b in expirees:
        annuler_reservation_comptoir(b, None, f"Réservation {b.numero_suivi} annulée : non payée avant la date limite de dépôt.")
        resultat["expirees"] = resultat.get("expirees", 0) + 1

    limite = maintenant + timezone.timedelta(hours=24)
    a_rappeler = Bagage.objects.filter(
        statut=Bagage.Statut.ENREGISTRE, statut_paiement=Bagage.Paiement.PAYE, rappel_depot_envoye=False,
        voyage__statut=Voyage.Statut.PLANIFIE, voyage__date_limite_depot__gt=maintenant,
        voyage__date_limite_depot__lte=limite,
    ).select_related("voyage", "client")
    for b in a_rappeler:
        if b.client:
            envoyer_courriel(
                b.client.email, f"Rappel : déposez votre bagage {b.numero_suivi}",
                f"Pensez à déposer votre bagage {b.numero_suivi} avant le "
                f"{timezone.localtime(b.voyage.date_limite_depot):%d/%m/%Y à %H:%M} au {b.voyage.lieu_depot}.",
                reverse("client_envoi", args=[b.numero_suivi]),
            )
        b.rappel_depot_envoye = True
        b.save(update_fields=["rappel_depot_envoye"])
        resultat["rappels_depot"] += 1
    return resultat


# --------------------------------------------------------------------------
# Envoi enregistré au comptoir par l'administrateur (paiement en espèces, etc.)
# --------------------------------------------------------------------------


@transaction.atomic
def creer_envoi_comptoir(admin, voyage, donnees, client_infos, mode, depose=True, request=None):
    """
    Crée l'envoi d'un client qui paie au comptoir.
    - Si un courriel est fourni : compte client trouvé ou créé (lien d'activation envoyé) → il suit
      son bagage dans son espace et reçoit les notifications.
    - Sinon : pas de compte, le client suit son bagage avec le numéro de suivi imprimé sur le reçu.
    Retourne (bagage, compte_cree).
    """
    import secrets as _secrets

    client, compte_cree = None, False
    courriel = (client_infos.get("courriel") or "").strip().lower()
    if courriel:
        client = Utilisateur.objects.filter(email__iexact=courriel).first()
        if client and client.role != Utilisateur.Role.CLIENT:
            raise ErreurMetier("Ce courriel appartient à un compte transporteur ou administrateur.")
        if client is None:
            client = Utilisateur(email=courriel, role=Utilisateur.Role.CLIENT, email_confirme=True,
                                 first_name=client_infos.get("prenom", ""), last_name=client_infos.get("nom", ""),
                                 telephone=client_infos.get("telephone", ""))
            client.set_password(_secrets.token_urlsafe(24))  # le client choisira le sien via le lien d'activation
            client.save()
            compte_cree = True

    bagage = creer_bagage(client, voyage, donnees)
    paiement = Paiement.objects.create(bagage=bagage, montant=bagage.prix, devise=bagage.devise, mode=mode, encaisse_par=admin)
    confirmer_paiement(paiement, reference=f"comptoir-{mode}-{paiement.pk}")
    EvenementBagage.objects.filter(bagage=bagage).update(auteur=admin)
    if depose:
        bagage.refresh_from_db()
        changer_statut(bagage, Bagage.Statut.DEPOSE, admin, notifier_client=False,
                       message=f"Bagage déposé au comptoir et payé ({paiement.get_mode_display().lower()}).")
    if not client:
        # Pas de compte : les infos de contact sont gardées dans l'historique pour le service client
        nom = f"{client_infos.get('prenom', '')} {client_infos.get('nom', '')}".strip()
        EvenementBagage.objects.create(bagage=bagage, statut=bagage.statut, auteur=admin,
                                       message=f"Expéditeur sans compte : {nom} — {client_infos.get('telephone', '')}"[:255])
        if client_infos.get("telephone"):
            envoyer_sms(client_infos["telephone"], f"Votre envoi {bagage.numero_suivi} est enregistré. Suivi : "
                        f"{url_absolue(reverse('suivi_detail', args=[bagage.numero_suivi]))}")
    if compte_cree:
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        lien = reverse("password_reset_confirm", args=[urlsafe_base64_encode(force_bytes(client.pk)),
                                                       default_token_generator.make_token(client)])
        envoyer_courriel(client.email, "Votre compte a été créé",
                         f"Bonjour {client.first_name},\n\nNous avons créé votre compte lors de votre envoi au comptoir. "
                         f"Choisissez votre mot de passe avec ce lien pour suivre votre bagage {bagage.numero_suivi} "
                         f"dans votre espace client :", lien)
    bagage.refresh_from_db()
    return bagage, compte_cree


# --------------------------------------------------------------------------
# Réservation en ligne, paiement au comptoir (tant que le paiement par carte est désactivé)
# --------------------------------------------------------------------------


@transaction.atomic
def reserver_paiement_comptoir(client, voyage, donnees):
    """Réservation en ligne : les kilos sont bloqués jusqu'à la date limite de dépôt, paiement au point de dépôt."""
    voyage = Voyage.objects.select_for_update().get(pk=voyage.pk)
    bagage = creer_bagage(client, voyage, donnees)
    bagage.paiement_au_comptoir = True
    bagage.save(update_fields=["paiement_au_comptoir"])
    EvenementBagage.objects.create(bagage=bagage, statut=Bagage.Statut.ENREGISTRE, auteur=client,
                                   message="Réservation enregistrée — à payer au point de dépôt.")
    from zoneinfo import ZoneInfo

    params = Parametres.charger()
    limite = timezone.localtime(voyage.date_limite_depot, ZoneInfo(voyage.pays_depart.fuseau))
    lien = reverse("client_envoi", args=[bagage.numero_suivi])
    if client:
        Notification.objects.create(destinataire=client, lien=lien,
                                    message=f"Réservation {bagage.numero_suivi} : {bagage.prix} {bagage.devise} à payer au dépôt")
        envoyer_courriel(
            client.email, f"Réservation {bagage.numero_suivi} — paiement au point de dépôt",
            f"Votre réservation est enregistrée et vos {bagage.poids} kg sont réservés sur le voyage "
            f"{voyage.ville_depart.nom} → {bagage.ville_livraison.nom}.\n\n"
            f"Numéro de réservation : {bagage.numero_suivi}\n"
            f"Montant à payer au dépôt : {bagage.prix} {bagage.devise} (espèces, carte au terminal ou virement)\n"
            f"Lieu de dépôt : {voyage.lieu_depot}\n"
            f"Date limite : {limite:%d/%m/%Y à %H:%M}\n\n"
            "Sans paiement avant la date limite, la réservation est annulée automatiquement. "
            f"Contact : {params.telephone}", lien)
    notifier_admins(f"Nouvelle réservation à encaisser au comptoir : {bagage.numero_suivi} ({bagage.prix} {bagage.devise})",
                    reverse("gestion_bagage", args=[bagage.numero_suivi]), courriel=False)
    return bagage


def corriger_poids(bagage, poids_pese, auteur, longueur=None, largeur=None, hauteur=None):
    """Pesée au comptoir : met à jour le poids réel (et les dimensions), recalcule le prix aux tarifs figés."""
    poids_pese = Decimal(str(poids_pese))
    pays = bagage.voyage.pays_arrivee
    if poids_pese <= 0:
        raise ErreurMetier("Le poids pesé doit être supérieur à 0.")
    if poids_pese > pays.poids_max:
        raise ErreurMetier(f"Le poids pesé dépasse le maximum autorisé pour {pays.nom} ({pays.poids_max} kg).")
    voyage = Voyage.objects.select_for_update().get(pk=bagage.voyage_id)
    restants = voyage.kilos_restants + (bagage.poids if bagage.a_encaisser and timezone.now() < voyage.date_limite_depot else 0)
    if poids_pese > restants:
        raise ErreurMetier(f"Capacité insuffisante : il ne reste que {restants} kg sur ce voyage pour ce bagage.")
    if longueur and largeur and hauteur:
        bagage.longueur_cm, bagage.largeur_cm, bagage.hauteur_cm = longueur, largeur, hauteur
    ancien_poids, ancien_prix = bagage.poids, bagage.prix
    pf = poids_facture(poids_pese, bagage.longueur_cm, bagage.largeur_cm, bagage.hauteur_cm)
    nouveau_prix = (bagage.frais_fixes + pf * bagage.tarif_kg).quantize(Decimal("0.01"))
    if poids_pese == ancien_poids and nouveau_prix == ancien_prix:
        return bagage
    bagage.poids, bagage.poids_facture, bagage.prix = poids_pese, pf, nouveau_prix
    bagage.save(update_fields=["poids", "poids_facture", "prix", "longueur_cm", "largeur_cm", "hauteur_cm"])
    EvenementBagage.objects.create(
        bagage=bagage, statut=bagage.statut, auteur=auteur,
        message=f"Pesée au comptoir : {ancien_poids} → {poids_pese} kg"
                + (f" (facturé {pf} kg, volumétrique)" if pf > poids_pese else "")
                + f", prix {ancien_prix} → {nouveau_prix} {bagage.devise}.")
    return bagage


@transaction.atomic
def encaisser_reservation(bagage, admin, mode, depose=True, poids_pese=None, longueur=None, largeur=None, hauteur=None):
    """L'admin encaisse au comptoir une réservation faite en ligne (après pesée éventuelle)."""
    if not bagage.a_encaisser:
        raise ErreurMetier("Cette réservation n'est pas en attente de paiement.")
    if bagage.voyage.statut != Voyage.Statut.PLANIFIE:
        raise ErreurMetier("Le voyage n'est plus planifié : déplacez l'envoi vers un autre voyage.")
    if poids_pese:
        corriger_poids(bagage, poids_pese, admin, longueur, largeur, hauteur)
        bagage.refresh_from_db()
    paiement = Paiement.objects.create(bagage=bagage, montant=bagage.prix, devise=bagage.devise, mode=mode, encaisse_par=admin)
    confirmer_paiement(paiement, reference=f"comptoir-{mode}-{paiement.pk}")
    bagage.refresh_from_db()
    if depose:
        changer_statut(bagage, Bagage.Statut.DEPOSE, admin, notifier_client=False,
                       message=f"Payé au comptoir ({paiement.get_mode_display().lower()}) et bagage déposé.")
    return bagage


def annuler_reservation_comptoir(bagage, auteur, message=None):
    """Annule une réservation non payée (aucun remboursement : rien n'a été encaissé)."""
    if not bagage.a_encaisser:
        raise ErreurMetier("Cette réservation est déjà payée ou annulée.")
    return changer_statut(bagage, Bagage.Statut.ANNULE, auteur,
                          message or f"Réservation {bagage.numero_suivi} annulée (non payée).")
