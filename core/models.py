"""
Données gérées par le site (section 4 du cahier des charges).
Chaque classe correspond à une table de la base de données.
"""
import secrets
import zoneinfo
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# --------------------------------------------------------------------------
# Utilisateurs et rôles
# --------------------------------------------------------------------------


class GestionnaireUtilisateurs(BaseUserManager):
    use_in_migrations = True

    def _creer(self, email, password, **extra):
        if not email:
            raise ValueError("Le courriel est obligatoire")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("role", Utilisateur.Role.CLIENT)
        return self._creer(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, role=Utilisateur.Role.ADMIN, email_confirme=True)
        return self._creer(email, password, **extra)


class Utilisateur(AbstractUser):
    class Role(models.TextChoices):
        CLIENT = "client", _("Client")
        TRANSPORTEUR = "transporteur", _("Transporteur")
        ADMIN = "admin", _("Administrateur")

    username = None
    email = models.EmailField(_("courriel"), unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CLIENT)
    telephone = models.CharField(_("téléphone"), max_length=30, blank=True)
    pays_residence = models.CharField(_("pays de résidence"), max_length=80, blank=True)
    langue = models.CharField(max_length=5, choices=settings.LANGUAGES, default="fr")
    email_confirme = models.BooleanField(default=False)
    notif_site = models.BooleanField(_("notifications dans le site"), default=True)
    notif_courriel = models.BooleanField(_("notifications par courriel"), default=True)
    notif_sms = models.BooleanField(_("notifications par SMS"), default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = GestionnaireUtilisateurs()

    class Meta:
        verbose_name = "utilisateur"

    def __str__(self):
        return self.get_full_name() or self.email

    @property
    def est_client(self):
        return self.role == self.Role.CLIENT

    @property
    def est_transporteur(self):
        return self.role == self.Role.TRANSPORTEUR

    @property
    def est_admin(self):
        return self.role == self.Role.ADMIN

    def espace_url(self):
        return reverse({"client": "client_tableau", "transporteur": "transporteur_voyages", "admin": "gestion_tableau"}[self.role])


class DestinataireEnregistre(models.Model):
    client = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name="destinataires")
    nom = models.CharField(max_length=150)
    telephone = models.CharField(max_length=30)
    adresse = models.CharField(max_length=255)
    courriel = models.EmailField(blank=True)

    def __str__(self):
        return f"{self.nom} — {self.telephone}"


# --------------------------------------------------------------------------
# Pays et villes desservis
# --------------------------------------------------------------------------


class Pays(models.Model):
    nom = models.CharField(max_length=80, unique=True)
    code = models.CharField(max_length=2, unique=True, help_text="Code ISO à 2 lettres, ex. DZ")
    devise = models.CharField(max_length=3, default="CAD")
    frais_fixes = models.DecimalField(_("frais fixes par bagage"), max_digits=8, decimal_places=2)
    tarif_kg = models.DecimalField(_("tarif par kilo"), max_digits=8, decimal_places=2)
    poids_max = models.DecimalField(_("poids maximum par bagage (kg)"), max_digits=6, decimal_places=2)
    delai_min = models.PositiveIntegerField(_("délai minimum (jours)"), default=3)
    delai_max = models.PositiveIntegerField(_("délai maximum (jours)"), default=7)
    objets_interdits = models.TextField(blank=True, help_text="Un objet par ligne")
    documents_douane = models.TextField(blank=True, help_text="Un document par ligne")
    fuseau = models.CharField(_("fuseau horaire"), max_length=50, default="UTC")
    actif = models.BooleanField(default=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "pays"
        ordering = ["nom"]

    def __str__(self):
        return self.nom

    def clean(self):
        self.code = (self.code or "").upper()
        self.devise = (self.devise or "").upper()
        if self.delai_max < self.delai_min:
            raise ValidationError({"delai_max": "Le délai maximum doit être supérieur ou égal au délai minimum."})
        try:
            zoneinfo.ZoneInfo(self.fuseau)
        except Exception:
            raise ValidationError({"fuseau": "Fuseau horaire inconnu (ex. Africa/Algiers)."})

    @property
    def drapeau(self):
        if len(self.code) != 2:
            return ""
        return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in self.code.upper())

    @property
    def delai_texte(self):
        return f"{self.delai_min} à {self.delai_max} jours"

    @property
    def liste_objets_interdits(self):
        return [o.strip() for o in self.objets_interdits.splitlines() if o.strip()]

    @property
    def liste_documents(self):
        return [o.strip() for o in self.documents_douane.splitlines() if o.strip()]

    def calculer_prix(self, poids):
        """Prix = frais fixes + (poids × tarif par kilo)."""
        poids = Decimal(str(poids))
        return (self.frais_fixes + poids * self.tarif_kg).quantize(Decimal("0.01"))

    def est_utilise(self):
        return Voyage.objects.filter(models.Q(ville_depart__pays=self) | models.Q(ville_arrivee__pays=self)).exists()

    def prochain_depart(self):
        return Voyage.reservables().filter(ville_arrivee__pays=self).order_by("depart").first()


class Ville(models.Model):
    pays = models.ForeignKey(Pays, on_delete=models.CASCADE, related_name="villes")
    nom = models.CharField(max_length=80)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["nom"]
        unique_together = [("pays", "nom")]

    def __str__(self):
        return f"{self.nom} ({self.pays.code})"


# --------------------------------------------------------------------------
# Voyages
# --------------------------------------------------------------------------


class Voyage(models.Model):
    class Moyen(models.TextChoices):
        AVION = "avion", _("Avion")
        CAMION = "camion", _("Camion")
        BATEAU = "bateau", _("Bateau")

    class Statut(models.TextChoices):
        PLANIFIE = "planifie", _("Planifié")
        EN_COURS = "en_cours", _("En cours")
        TERMINE = "termine", _("Terminé")
        ANNULE = "annule", _("Annulé")

    ville_depart = models.ForeignKey(Ville, on_delete=models.PROTECT, related_name="voyages_depart")
    ville_arrivee = models.ForeignKey(Ville, on_delete=models.PROTECT, related_name="voyages_arrivee")
    depart = models.DateTimeField(_("date et heure de départ"))
    arrivee_prevue = models.DateTimeField(_("date et heure d'arrivée prévue"))
    date_limite_depot = models.DateTimeField(_("date limite de dépôt"))
    lieu_depot = models.CharField(_("lieu de dépôt"), max_length=255)
    heure_depot = models.CharField(_("heure de dépôt"), max_length=80, blank=True, help_text="ex. de 10 h à 17 h")
    transporteur = models.ForeignKey(
        Utilisateur, on_delete=models.PROTECT, related_name="voyages", null=True, blank=True,
        limit_choices_to={"role": Utilisateur.Role.TRANSPORTEUR},
    )
    moyen = models.CharField(max_length=10, choices=Moyen.choices, default=Moyen.AVION)
    capacite_kg = models.DecimalField(_("capacité totale (kg)"), max_digits=8, decimal_places=2)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.PLANIFIE)
    demarre_le = models.DateTimeField(null=True, blank=True)
    termine_le = models.DateTimeField(null=True, blank=True)
    dernier_rappel_position = models.DateTimeField(null=True, blank=True)
    derniere_alerte_admin = models.DateTimeField(null=True, blank=True)
    alerte_presque_complet = models.BooleanField(default=False)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["depart"]

    def __str__(self):
        return f"{self.ville_depart.nom} → {self.ville_arrivee.nom} · {timezone.localtime(self.depart):%d/%m/%Y %H:%M}"

    def get_absolute_url(self):
        return reverse("gestion_voyage_modifier", args=[self.pk])

    def clean(self):
        erreurs = {}
        if self.depart and self.arrivee_prevue and self.arrivee_prevue <= self.depart:
            erreurs["arrivee_prevue"] = "La date d'arrivée doit être après la date de départ."
        if self.depart and self.date_limite_depot and self.date_limite_depot > self.depart:
            erreurs["date_limite_depot"] = "La date limite de dépôt doit être avant le départ."
        if self.ville_depart_id and self.ville_arrivee_id:
            pd, pa = self.ville_depart.pays, self.ville_arrivee.pays
            if pd == pa:
                erreurs["ville_arrivee"] = "Les pays de départ et d'arrivée doivent être différents."
            if not pd.actif or not pa.actif:
                erreurs["ville_depart"] = "Les pays de départ et d'arrivée doivent être actifs."
        if self.capacite_kg is not None and self.capacite_kg <= 0:
            erreurs["capacite_kg"] = "La capacité doit être positive."
        if self.pk and self.capacite_kg is not None and self.capacite_kg < self.kilos_reserves:
            erreurs["capacite_kg"] = f"Capacité inférieure aux kilos déjà réservés ({self.kilos_reserves} kg)."
        if erreurs:
            raise ValidationError(erreurs)

    # -- pays (raccourcis)
    @property
    def pays_depart(self):
        return self.ville_depart.pays

    @property
    def pays_arrivee(self):
        return self.ville_arrivee.pays

    # -- capacité
    @property
    def kilos_reserves(self):
        total = self.bagages.filter(statut_paiement=Bagage.Paiement.PAYE).exclude(
            statut=Bagage.Statut.ANNULE
        ).aggregate(t=Sum("poids"))["t"]
        return total or Decimal("0")

    @property
    def kilos_restants(self):
        return max(self.capacite_kg - self.kilos_reserves, Decimal("0"))

    @property
    def taux_remplissage(self):
        if not self.capacite_kg:
            return 0
        return int(self.kilos_reserves * 100 / self.capacite_kg)

    @property
    def est_complet(self):
        return self.kilos_restants <= 0

    @property
    def reservations_ouvertes(self):
        return (
            self.statut == self.Statut.PLANIFIE
            and timezone.now() < self.date_limite_depot
            and not self.est_complet
            and self.pays_depart.actif
            and self.pays_arrivee.actif
        )

    @property
    def etat_affiche(self):
        if self.statut == self.Statut.PLANIFIE and self.est_complet:
            return "Complet"
        return self.get_statut_display()

    @classmethod
    def reservables(cls):
        return cls.objects.filter(
            statut=cls.Statut.PLANIFIE,
            date_limite_depot__gt=timezone.now(),
            ville_depart__pays__actif=True,
            ville_arrivee__pays__actif=True,
        ).select_related("ville_depart__pays", "ville_arrivee__pays")

    # -- positions
    @property
    def derniere_position(self):
        return self.positions.order_by("-envoyee_le").first()

    @property
    def minutes_depuis_position(self):
        ref = self.derniere_position.envoyee_le if self.derniere_position else self.demarre_le
        if not ref:
            return None
        return int((timezone.now() - ref).total_seconds() // 60)

    def fuseau_depart(self):
        return self.pays_depart.fuseau

    def fuseau_arrivee(self):
        return self.pays_arrivee.fuseau


class Position(models.Model):
    voyage = models.ForeignKey(Voyage, on_delete=models.CASCADE, related_name="positions")
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    lieu = models.CharField(_("nom du lieu"), max_length=150, blank=True)
    commentaire = models.CharField(max_length=255, blank=True)
    envoyee_le = models.DateTimeField(default=timezone.now)
    transporteur = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ["envoyee_le"]

    def __str__(self):
        return f"{self.lieu or f'{self.latitude}, {self.longitude}'} — {self.envoyee_le:%d/%m %H:%M}"


# --------------------------------------------------------------------------
# Bagages (envois)
# --------------------------------------------------------------------------

ALPHABET_SUIVI = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans 0/O, 1/I


def generer_numero_suivi():
    while True:
        numero = "BG-" + "".join(secrets.choice(ALPHABET_SUIVI) for _ in range(8))
        if not Bagage.objects.filter(numero_suivi=numero).exists():
            return numero


def generer_code_remise():
    return f"{secrets.randbelow(1_000_000):06d}"


class Bagage(models.Model):
    class Statut(models.TextChoices):
        ENREGISTRE = "enregistre", _("Enregistré")
        DEPOSE = "depose", _("Déposé")
        CHARGE = "charge", _("Chargé")
        EN_TRANSIT = "en_transit", _("En transit")
        ARRIVE = "arrive", _("Arrivé à destination")
        LIVRE = "livre", _("Livré")
        INCIDENT = "incident", _("Incident en cours")
        PERDU = "perdu", _("Perdu")
        ANNULE = "annule", _("Annulé")

    class Paiement(models.TextChoices):
        EN_ATTENTE = "en_attente", _("En attente")
        PAYE = "paye", _("Payé")
        ECHOUE = "echoue", _("Échoué")
        REMBOURSE = "rembourse", _("Remboursé")

    # Étapes de la barre de progression
    ETAPES = [
        ("enregistre", _("Enregistré")),
        ("depose", _("Déposé")),
        ("en_transit", _("En transit")),
        ("arrive", _("Arrivé")),
        ("livre", _("Livré")),
    ]
    _RANG = {"enregistre": 0, "depose": 1, "charge": 1, "en_transit": 2, "arrive": 3, "livre": 4}

    numero_suivi = models.CharField(max_length=12, unique=True, default=generer_numero_suivi, editable=False)
    client = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, related_name="bagages")
    voyage = models.ForeignKey(Voyage, on_delete=models.PROTECT, related_name="bagages")
    description = models.CharField(_("description du contenu"), max_length=255)
    poids = models.DecimalField(_("poids (kg)"), max_digits=6, decimal_places=2)
    longueur_cm = models.PositiveIntegerField(null=True, blank=True)
    largeur_cm = models.PositiveIntegerField(null=True, blank=True)
    hauteur_cm = models.PositiveIntegerField(null=True, blank=True)
    valeur_declaree = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    photo_depot = models.ImageField(upload_to="bagages/depot/", null=True, blank=True)
    photo_livraison = models.ImageField(upload_to="bagages/livraison/", null=True, blank=True)
    dest_nom = models.CharField(_("nom du destinataire"), max_length=150)
    dest_telephone = models.CharField(_("téléphone du destinataire"), max_length=30)
    dest_adresse = models.CharField(_("adresse du destinataire"), max_length=255)
    dest_courriel = models.EmailField(_("courriel du destinataire"), blank=True)
    code_remise = models.CharField(max_length=6, default=generer_code_remise, editable=False)
    # Prix figé au moment de la réservation / du paiement
    frais_fixes = models.DecimalField(max_digits=8, decimal_places=2)
    tarif_kg = models.DecimalField(max_digits=8, decimal_places=2)
    prix = models.DecimalField(max_digits=10, decimal_places=2)
    devise = models.CharField(max_length=3)
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.ENREGISTRE)
    statut_paiement = models.CharField(max_length=12, choices=Paiement.choices, default=Paiement.EN_ATTENTE)
    choix_requis = models.BooleanField(default=False, help_text="Voyage annulé : le client doit choisir")
    rappel_depot_envoye = models.BooleanField(default=False)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return self.numero_suivi

    def get_absolute_url(self):
        return reverse("client_envoi", args=[self.numero_suivi])

    @property
    def rang(self):
        return self._RANG.get(self.statut, -1)

    @property
    def dest_nom_masque(self):
        """Nom masqué pour la page publique (ex. S*** B.)."""
        parties = self.dest_nom.split()
        if not parties:
            return ""
        prenom = parties[0][0].upper() + "***"
        nom = (" " + parties[-1][0].upper() + ".") if len(parties) > 1 else ""
        return prenom + nom

    @property
    def annulable(self):
        return (
            self.statut == self.Statut.ENREGISTRE
            and self.statut_paiement == self.Paiement.PAYE
            and timezone.now() < self.voyage.date_limite_depot
        ) or self.choix_requis

    @property
    def est_actif(self):
        return self.statut not in (self.Statut.LIVRE, self.Statut.ANNULE, self.Statut.PERDU)

    @property
    def dimensions(self):
        if self.longueur_cm and self.largeur_cm and self.hauteur_cm:
            return f"{self.longueur_cm} × {self.largeur_cm} × {self.hauteur_cm} cm"
        return ""


class EvenementBagage(models.Model):
    """Historique daté de chaque changement (traçabilité : date, heure, auteur)."""

    bagage = models.ForeignKey(Bagage, on_delete=models.CASCADE, related_name="evenements")
    statut = models.CharField(max_length=12, choices=Bagage.Statut.choices)
    message = models.CharField(max_length=255)
    auteur = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True)
    cree_le = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["cree_le", "pk"]


class AbonnementSuivi(models.Model):
    bagage = models.ForeignKey(Bagage, on_delete=models.CASCADE, related_name="abonnements")
    courriel = models.EmailField()
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("bagage", "courriel")]


class Incident(models.Model):
    class Type(models.TextChoices):
        RETARD = "retard", _("Retard")
        DOUANE = "douane", _("Blocage en douane")
        ENDOMMAGE = "endommage", _("Bagage endommagé")
        INTROUVABLE = "introuvable", _("Bagage introuvable")
        AUTRE = "autre", _("Autre")

    class Etat(models.TextChoices):
        OUVERT = "ouvert", _("Ouvert")
        RETROUVE = "retrouve", _("Retrouvé")
        PERDU = "perdu", _("Perdu")
        RESOLU = "resolu", _("Résolu")

    voyage = models.ForeignKey(Voyage, on_delete=models.CASCADE, related_name="incidents")
    bagage = models.ForeignKey(Bagage, on_delete=models.CASCADE, related_name="incidents", null=True, blank=True)
    type = models.CharField(max_length=12, choices=Type.choices)
    commentaire = models.TextField(blank=True)
    etat = models.CharField(max_length=10, choices=Etat.choices, default=Etat.OUVERT)
    signale_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True)
    statut_avant = models.CharField(max_length=12, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)
    traite_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-cree_le"]


# --------------------------------------------------------------------------
# Paiements, notifications, paramètres
# --------------------------------------------------------------------------


class Paiement(models.Model):
    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", _("En attente")
        PAYE = "paye", _("Payé")
        ECHOUE = "echoue", _("Échoué")
        REMBOURSE = "rembourse", _("Remboursé")

    class Mode(models.TextChoices):
        CARTE = "carte", _("Carte en ligne (Stripe)")
        ESPECES = "especes", _("Espèces")
        TERMINAL = "terminal", _("Terminal de paiement (comptoir)")
        VIREMENT = "virement", _("Virement / Interac")

    bagage = models.ForeignKey(Bagage, on_delete=models.CASCADE, related_name="paiements")
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.CARTE)
    encaisse_par = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    devise = models.CharField(max_length=3)
    reference_stripe = models.CharField(max_length=255, blank=True)
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE)
    cree_le = models.DateTimeField(auto_now_add=True)
    paye_le = models.DateTimeField(null=True, blank=True)
    rembourse_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-cree_le"]

    @property
    def numero_recu(self):
        return f"R-{self.cree_le:%Y%m}-{self.pk:05d}"


class Notification(models.Model):
    class Canal(models.TextChoices):
        SITE = "site", _("Site")
        COURRIEL = "courriel", _("Courriel")
        SMS = "sms", _("SMS")

    destinataire = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=255)
    lien = models.CharField(max_length=255, blank=True)
    canal = models.CharField(max_length=10, choices=Canal.choices, default=Canal.SITE)
    lue = models.BooleanField(default=False)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]


class MessageContact(models.Model):
    nom = models.CharField(max_length=150)
    courriel = models.EmailField()
    sujet = models.CharField(max_length=150)
    message = models.TextField()
    traite = models.BooleanField(default=False)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]


class AvisClient(models.Model):
    nom = models.CharField(max_length=80)
    ville = models.CharField(max_length=80, blank=True)
    note = models.PositiveSmallIntegerField(default=5)
    texte = models.TextField()
    publie = models.BooleanField(default=True)


class Parametres(models.Model):
    """Paramètres du site (une seule ligne)."""

    nom_entreprise = models.CharField(max_length=100, default="Talaouglid")
    telephone = models.CharField(max_length=30, default="+1 514 000-0000")
    courriel = models.EmailField(default="contact@talaouglid.com")
    adresse_depot = models.CharField(max_length=255, default="1234 rue Exemple, Montréal (QC)")
    horaires = models.CharField(max_length=255, default="Lundi au samedi, 10 h à 18 h")
    rappel_position_heures = models.PositiveIntegerField(_("fréquence du rappel de position (h)"), default=2)
    alerte_sans_position_heures = models.PositiveIntegerField(_("délai d'alerte sans position (h)"), default=4)
    fermeture_reservations_heures = models.PositiveIntegerField(_("fermeture des réservations avant départ (h)"), default=24)
    seuil_presque_complet = models.PositiveIntegerField(default=90, help_text="% de remplissage déclenchant une alerte")
    texte_courriel_confirmation = models.TextField(
        default="Merci pour votre réservation. Déposez votre bagage avant la date limite indiquée ci-dessous."
    )
    conditions_generales = models.TextField(
        default=(
            "1. Le prix est figé au moment du paiement.\n"
            "2. Annulation possible jusqu'à la date limite de dépôt, avec remboursement intégral.\n"
            "3. Après le dépôt, l'annulation en ligne n'est plus possible.\n"
            "4. Les objets interdits du pays de destination sont refusés au dépôt.\n"
            "5. Le bagage est remis uniquement contre le code à 6 chiffres envoyé au destinataire."
        )
    )
    politique_confidentialite = models.TextField(
        default=(
            "Conformément à la Loi 25 (Québec), vos données ne servent qu'au traitement de vos envois. "
            "Le nom du destinataire est masqué sur la page publique de suivi. Vous pouvez supprimer votre "
            "compte à tout moment depuis votre profil."
        )
    )

    class Meta:
        verbose_name_plural = "paramètres"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def charger(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
