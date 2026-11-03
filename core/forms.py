from decimal import Decimal

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    Bagage,
    DestinataireEnregistre,
    Incident,
    MessageContact,
    Parametres,
    Pays,
    Utilisateur,
    Ville,
    Voyage,
)

DT_WIDGET = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


class BootstrapMixin:
    """Ajoute les classes Bootstrap à tous les champs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in self.fields.values():
            w = champ.widget
            if isinstance(w, (forms.CheckboxInput,)):
                w.attrs.setdefault("class", "form-check-input")
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs.setdefault("class", "form-select")
            else:
                w.attrs.setdefault("class", "form-control")


# --------------------------------------------------------------------------
# Comptes
# --------------------------------------------------------------------------


class ConnexionForm(BootstrapMixin, AuthenticationForm):
    username = forms.EmailField(label="Courriel", widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}))


class InscriptionForm(BootstrapMixin, forms.ModelForm):
    password1 = forms.CharField(label="Mot de passe", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    password2 = forms.CharField(label="Confirmer le mot de passe", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    accepte_conditions = forms.BooleanField(
        label="J'accepte les conditions générales et la politique de confidentialité", required=True
    )

    class Meta:
        model = Utilisateur
        fields = ["first_name", "last_name", "email", "telephone", "pays_residence"]
        labels = {"first_name": "Prénom", "last_name": "Nom"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ("first_name", "last_name", "telephone"):
            self.fields[f].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if Utilisateur.objects.filter(email__iexact=email).exists():
            raise ValidationError("Un compte existe déjà avec ce courriel.")
        return email

    def clean(self):
        donnees = super().clean()
        p1, p2 = donnees.get("password1"), donnees.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Les mots de passe ne correspondent pas.")
        if p1:
            from django.contrib.auth.password_validation import validate_password

            try:
                validate_password(p1, Utilisateur(email=donnees.get("email", ""), first_name=donnees.get("first_name", "")))
            except ValidationError as e:
                self.add_error("password1", e)
        return donnees

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.role = Utilisateur.Role.CLIENT
        if commit:
            user.save()
        return user


class ProfilForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Utilisateur
        fields = ["first_name", "last_name", "telephone", "pays_residence", "langue", "notif_site", "notif_courriel", "notif_sms"]
        labels = {"first_name": "Prénom", "last_name": "Nom", "langue": "Langue"}


class DestinataireForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = DestinataireEnregistre
        fields = ["nom", "telephone", "adresse", "courriel"]


class TransporteurForm(BootstrapMixin, forms.ModelForm):
    password = forms.CharField(label="Mot de passe provisoire", widget=forms.PasswordInput, min_length=8)

    class Meta:
        model = Utilisateur
        fields = ["first_name", "last_name", "email", "telephone"]
        labels = {"first_name": "Prénom", "last_name": "Nom"}

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = Utilisateur.Role.TRANSPORTEUR
        user.email_confirme = True
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


# --------------------------------------------------------------------------
# Public
# --------------------------------------------------------------------------


class SimulateurForm(BootstrapMixin, forms.Form):
    pays = forms.ModelChoiceField(queryset=Pays.objects.none(), label="Pays d'arrivée", empty_label="Choisir un pays")
    ville = forms.ModelChoiceField(queryset=Ville.objects.none(), label="Ville d'arrivée", required=False, empty_label="Toutes les villes")
    poids = forms.DecimalField(label="Poids (kg)", min_value=Decimal("0.1"), max_digits=6, decimal_places=2)
    longueur = forms.IntegerField(label="Longueur (cm)", required=False, min_value=1)
    largeur = forms.IntegerField(label="Largeur (cm)", required=False, min_value=1)
    hauteur = forms.IntegerField(label="Hauteur (cm)", required=False, min_value=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pays"].queryset = Pays.objects.filter(actif=True)
        self.fields["ville"].queryset = Ville.objects.filter(pays__actif=True)


class ContactForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = MessageContact
        fields = ["nom", "courriel", "sujet", "message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 4})}


class AbonnementForm(BootstrapMixin, forms.Form):
    courriel = forms.EmailField(label="Votre courriel")


# --------------------------------------------------------------------------
# Réservation (4 étapes)
# --------------------------------------------------------------------------


class EtapeDestinationForm(BootstrapMixin, forms.Form):
    pays = forms.ModelChoiceField(queryset=Pays.objects.none(), label="Pays d'arrivée")
    ville = forms.ModelChoiceField(queryset=Ville.objects.none(), label="Ville d'arrivée", required=False)
    voyage = forms.ModelChoiceField(queryset=Voyage.objects.none(), label="Voyage", widget=forms.RadioSelect)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pays"].queryset = Pays.objects.filter(actif=True)
        self.fields["ville"].queryset = Ville.objects.filter(pays__actif=True)
        self.fields["voyage"].queryset = Voyage.reservables()
        self.fields["voyage"].widget.attrs["class"] = "form-check-input"

    def clean(self):
        d = super().clean()
        v, p = d.get("voyage"), d.get("pays")
        if v and p and v.ville_arrivee.pays_id != p.pk:
            self.add_error("voyage", "Ce voyage ne va pas vers le pays choisi.")
        if v and d.get("ville") and not v.dessert(d["ville"]):
            self.add_error("voyage", f"Ce voyage ne dessert pas {d['ville'].nom}.")
        if v and not v.reservations_ouvertes:
            self.add_error("voyage", "Ce voyage n'est plus réservable (complet ou date limite dépassée).")
        return d


class EtapeBagageForm(BootstrapMixin, forms.Form):
    description = forms.CharField(label="Description du contenu", max_length=255)
    poids = forms.DecimalField(label="Poids (kg)", min_value=Decimal("0.1"), max_digits=6, decimal_places=2)
    longueur_cm = forms.IntegerField(label="Longueur (cm)", required=False, min_value=1)
    largeur_cm = forms.IntegerField(label="Largeur (cm)", required=False, min_value=1)
    hauteur_cm = forms.IntegerField(label="Hauteur (cm)", required=False, min_value=1)
    valeur_declaree = forms.DecimalField(label="Valeur déclarée", min_value=0, max_digits=10, decimal_places=2, initial=0)
    photo = forms.ImageField(label="Photo (optionnelle)", required=False)

    def __init__(self, *args, voyage=None, **kwargs):
        self.voyage = voyage
        super().__init__(*args, **kwargs)

    def clean_poids(self):
        poids = self.cleaned_data["poids"]
        if self.voyage:
            pays = self.voyage.pays_arrivee
            if poids > pays.poids_max:
                raise ValidationError(f"Le poids maximum pour {pays.nom} est de {pays.poids_max} kg.")
            if poids > self.voyage.kilos_restants:
                raise ValidationError(f"Il ne reste que {self.voyage.kilos_restants} kg sur ce voyage.")
        return poids


class EtapeDestinataireForm(BootstrapMixin, forms.Form):
    enregistre = forms.ModelChoiceField(queryset=DestinataireEnregistre.objects.none(), required=False,
                                        label="Destinataire enregistré", empty_label="— Nouveau destinataire —")
    dest_nom = forms.CharField(label="Nom complet", max_length=150, required=False)
    dest_telephone = forms.CharField(label="Téléphone", max_length=30, required=False)
    dest_adresse = forms.CharField(label="Adresse", max_length=255, required=False)
    dest_courriel = forms.EmailField(label="Courriel (optionnel)", required=False)
    enregistrer = forms.BooleanField(label="Enregistrer ce destinataire pour mes prochains envois", required=False)

    def __init__(self, *args, client=None, **kwargs):
        super().__init__(*args, **kwargs)
        if client:
            self.fields["enregistre"].queryset = client.destinataires.all()

    def clean(self):
        d = super().clean()
        e = d.get("enregistre")
        if e:
            d.update(dest_nom=e.nom, dest_telephone=e.telephone, dest_adresse=e.adresse, dest_courriel=e.courriel)
        for champ in ("dest_nom", "dest_telephone", "dest_adresse"):
            if not d.get(champ):
                self.add_error(champ, "Ce champ est obligatoire.")
        return d


# --------------------------------------------------------------------------
# Transporteur
# --------------------------------------------------------------------------


class PositionForm(BootstrapMixin, forms.Form):
    voyage = forms.ModelChoiceField(queryset=Voyage.objects.none(), widget=forms.HiddenInput)
    latitude = forms.FloatField(required=False, widget=forms.HiddenInput)
    longitude = forms.FloatField(required=False, widget=forms.HiddenInput)
    lieu = forms.CharField(label="Nom du lieu (optionnel)", max_length=150, required=False,
                           widget=forms.TextInput(attrs={"placeholder": "ex. Aéroport de Montréal"}))
    commentaire = forms.CharField(label="Commentaire", max_length=255, required=False)


class IncidentForm(BootstrapMixin, forms.Form):
    type = forms.ChoiceField(choices=Incident.Type.choices, label="Type d'incident")
    numero = forms.CharField(label="Numéro du bagage (laisser vide si tout le voyage)", required=False)
    commentaire = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)


class LivraisonForm(BootstrapMixin, forms.Form):
    code = forms.CharField(label="Code de remise à 6 chiffres", min_length=6, max_length=6,
                           widget=forms.TextInput(attrs={"inputmode": "numeric", "pattern": "[0-9]{6}", "autocomplete": "off"}))
    photo = forms.ImageField(label="Photo de la remise", required=False,
                             widget=forms.ClearableFileInput(attrs={"accept": "image/*", "capture": "environment"}))


# --------------------------------------------------------------------------
# Administration
# --------------------------------------------------------------------------


class PaysForm(BootstrapMixin, forms.ModelForm):
    villes = forms.CharField(
        label="Villes desservies",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Alger; 36.75; 3.06\nOran; 35.70; -0.63\nTizi-Ouzou"}),
        help_text="Une ville par ligne. Coordonnées optionnelles : Nom; latitude; longitude",
    )

    class Meta:
        model = Pays
        fields = ["nom", "code", "devise", "frais_fixes", "tarif_kg", "poids_max", "delai_min", "delai_max",
                  "fuseau", "objets_interdits", "documents_douane", "actif"]
        widgets = {"objets_interdits": forms.Textarea(attrs={"rows": 3}), "documents_douane": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            lignes = []
            for v in self.instance.villes.all():
                lignes.append(f"{v.nom}; {v.latitude}; {v.longitude}" if v.latitude is not None else v.nom)
            self.initial["villes"] = "\n".join(lignes)

    def clean_villes(self):
        resultat = []
        for ligne in self.cleaned_data["villes"].splitlines():
            parts = [p.strip() for p in ligne.split(";")]
            if not parts[0]:
                continue
            lat = lng = None
            if len(parts) >= 3 and parts[1] and parts[2]:
                try:
                    lat, lng = float(parts[1].replace(",", ".")), float(parts[2].replace(",", "."))
                except ValueError:
                    raise ValidationError(f"Coordonnées invalides pour « {parts[0]} ».")
            resultat.append((parts[0], lat, lng))
        if not resultat:
            raise ValidationError("Indiquez au moins une ville.")
        return resultat

    def save(self, commit=True):
        pays = super().save(commit=True)
        noms = []
        for nom, lat, lng in self.cleaned_data["villes"]:
            Ville.objects.update_or_create(pays=pays, nom=nom, defaults={"latitude": lat, "longitude": lng})
            noms.append(nom)
        # Villes retirées : supprimées seulement si aucun voyage ne les utilise
        for v in pays.villes.exclude(nom__in=noms):
            if not v.voyages_depart.exists() and not v.voyages_arrivee.exists():
                v.delete()
        return pays


class VoyageForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Voyage
        fields = ["ville_depart", "ville_arrivee", "autres_villes", "depart", "arrivee_prevue", "date_limite_depot", "lieu_depot",
                  "heure_depot", "capacite_kg", "transporteur", "moyen"]
        widgets = {"depart": DT_WIDGET, "arrivee_prevue": DT_WIDGET, "date_limite_depot": DT_WIDGET,
                   "autres_villes": forms.CheckboxSelectMultiple}
        help_texts = {"date_limite_depot": "Laisser vide : 24 h avant le départ (voir paramètres)."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        villes = Ville.objects.filter(pays__actif=True).select_related("pays").order_by("pays__nom", "nom")
        self.fields["ville_depart"].queryset = villes
        self.fields["ville_arrivee"].queryset = villes
        self.fields["autres_villes"].queryset = villes
        self.fields["autres_villes"].widget.attrs.pop("class", None)
        self.fields["transporteur"].queryset = Utilisateur.objects.filter(role=Utilisateur.Role.TRANSPORTEUR, is_active=True)
        self.fields["date_limite_depot"].required = False
        for f in ("depart", "arrivee_prevue", "date_limite_depot"):
            self.fields[f].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean(self):
        d = self.cleaned_data
        principale, autres = d.get("ville_arrivee"), d.get("autres_villes")
        if principale and autres:
            hors_pays = [v.nom for v in autres if v.pays_id != principale.pays_id]
            if hors_pays:
                self.add_error("autres_villes", f"Ces villes ne sont pas en {principale.pays.nom} : {', '.join(hors_pays)}.")
            d["autres_villes"] = [v for v in autres if v.pk != principale.pk]
        if d.get("depart") and not d.get("date_limite_depot"):
            heures = Parametres.charger().fermeture_reservations_heures
            d["date_limite_depot"] = d["depart"] - timezone.timedelta(hours=heures)
            self.instance.date_limite_depot = d["date_limite_depot"]
        return super().clean()


class ParametresForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Parametres
        fields = "__all__"
        widgets = {
            "texte_courriel_confirmation": forms.Textarea(attrs={"rows": 3}),
            "conditions_generales": forms.Textarea(attrs={"rows": 6}),
            "politique_confidentialite": forms.Textarea(attrs={"rows": 4}),
        }


class StatutBagageForm(BootstrapMixin, forms.Form):
    statut = forms.ChoiceField(choices=Bagage.Statut.choices, label="Nouveau statut")
    message = forms.CharField(label="Message (optionnel)", required=False, max_length=255)


class DeplacerBagageForm(BootstrapMixin, forms.Form):
    voyage = forms.ModelChoiceField(queryset=Voyage.objects.none(), label="Nouveau voyage")

    def __init__(self, *args, bagage=None, **kwargs):
        super().__init__(*args, **kwargs)
        if bagage:
            self.fields["voyage"].queryset = Voyage.objects.filter(
                statut=Voyage.Statut.PLANIFIE, ville_arrivee__pays=bagage.voyage.ville_arrivee.pays
            ).exclude(pk=bagage.voyage_id)


class EnvoiComptoirForm(BootstrapMixin, forms.Form):
    """Envoi enregistré par l'administrateur pour un client qui paie au comptoir."""

    # Expéditeur
    courriel = forms.EmailField(label="Courriel du client", required=False,
                                help_text="Recommandé : un compte est créé (ou retrouvé) pour qu'il suive son bagage "
                                          "dans son espace. Sans courriel, il suit avec le numéro imprimé sur le reçu.")
    prenom = forms.CharField(label="Prénom", max_length=150)
    nom = forms.CharField(label="Nom", max_length=150)
    telephone = forms.CharField(label="Téléphone", max_length=30)
    # Voyage et bagage
    voyage = forms.ModelChoiceField(queryset=Voyage.objects.none(), label="Voyage")
    ville_destination = forms.ModelChoiceField(queryset=Ville.objects.none(), label="Ville de livraison", required=False,
                                               empty_label="Ville principale du voyage")
    description = forms.CharField(label="Description du contenu", max_length=255)
    poids = forms.DecimalField(label="Poids (kg)", min_value=Decimal("0.1"), max_digits=6, decimal_places=2)
    longueur_cm = forms.IntegerField(label="Longueur (cm)", required=False, min_value=1)
    largeur_cm = forms.IntegerField(label="Largeur (cm)", required=False, min_value=1)
    hauteur_cm = forms.IntegerField(label="Hauteur (cm)", required=False, min_value=1)
    valeur_declaree = forms.DecimalField(label="Valeur déclarée", min_value=0, max_digits=10, decimal_places=2, initial=0)
    photo = forms.ImageField(label="Photo du bagage", required=False)
    # Destinataire
    dest_nom = forms.CharField(label="Nom du destinataire", max_length=150)
    dest_telephone = forms.CharField(label="Téléphone du destinataire", max_length=30)
    dest_adresse = forms.CharField(label="Adresse du destinataire", max_length=255)
    dest_courriel = forms.EmailField(label="Courriel du destinataire", required=False)
    # Paiement
    mode = forms.ChoiceField(label="Mode de paiement", choices=[
        ("especes", "Espèces"), ("terminal", "Terminal de paiement (comptoir)"), ("virement", "Virement / Interac")])
    depose = forms.BooleanField(label="Le bagage est déposé maintenant au comptoir", required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["voyage"].queryset = Voyage.reservables().order_by("depart")
        self.fields["ville_destination"].queryset = Ville.objects.filter(pays__actif=True).select_related("pays").order_by("pays__nom", "nom")
        self.fields["voyage"].label_from_instance = lambda v: (
            f"{v.ville_depart.nom} → {v.destinations_texte} · {timezone.localtime(v.depart):%d/%m/%Y %H:%M} "
            f"· {v.kilos_restants:.0f} kg restants · {v.pays_arrivee.frais_fixes} + {v.pays_arrivee.tarif_kg}/kg")

    def clean(self):
        d = super().clean()
        v, poids = d.get("voyage"), d.get("poids")
        if v and poids:
            pays = v.pays_arrivee
            if poids > pays.poids_max:
                self.add_error("poids", f"Le poids maximum pour {pays.nom} est de {pays.poids_max} kg.")
            elif poids > v.kilos_restants:
                self.add_error("poids", f"Il ne reste que {v.kilos_restants} kg sur ce voyage.")
        if v and d.get("ville_destination") and not v.dessert(d["ville_destination"]):
            self.add_error("ville_destination", f"Ce voyage dessert : {v.destinations_texte}.")
        return d
