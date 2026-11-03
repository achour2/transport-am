"""Crée des données de démonstration : `python manage.py donnees_demo`."""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from core import services
from core.models import AvisClient, Bagage, Paiement, Parametres, Pays, Position, Utilisateur, Ville, Voyage

PAYS = [
    # nom, code, devise, frais, tarif, max, dmin, dmax, fuseau, villes
    ("Canada", "CA", "CAD", 20, 8, 30, 5, 7, "America/Toronto",
     [("Montréal", 45.5019, -73.5674), ("Toronto", 43.6532, -79.3832), ("Québec", 46.8139, -71.2080)]),
    ("Algérie", "DZ", "CAD", 20, 8, 30, 5, 7, "Africa/Algiers",
     [("Alger", 36.7538, 3.0588), ("Oran", 35.6971, -0.6308), ("Tizi-Ouzou", 36.7169, 4.0497), ("Constantine", 36.3650, 6.6147)]),
    ("France", "FR", "CAD", 15, 7, 30, 3, 5, "Europe/Paris",
     [("Paris", 48.8566, 2.3522), ("Lyon", 45.7640, 4.8357), ("Marseille", 43.2965, 5.3698)]),
    ("Maroc", "MA", "CAD", 20, Decimal("8.50"), 25, 5, 8, "Africa/Casablanca",
     [("Casablanca", 33.5731, -7.5898), ("Rabat", 34.0209, -6.8416)]),
    ("Tunisie", "TN", "CAD", 20, Decimal("8.50"), 25, 6, 9, "Africa/Tunis",
     [("Tunis", 36.8065, 10.1815), ("Sfax", 34.7406, 10.7603)]),
]
INTERDITS = "Produits inflammables ou explosifs\nArmes et munitions\nMédicaments sans ordonnance\nArgent liquide et bijoux de valeur\nProduits alimentaires frais"
DOCUMENTS = "Copie de la pièce d'identité de l'expéditeur\nListe détaillée du contenu\nFactures pour les objets neufs"


class Command(BaseCommand):
    help = "Charge des données de démonstration (pays, voyages, comptes, envois)."

    def add_arguments(self, parser):
        parser.add_argument("--reinitialiser", action="store_true", help="Supprime d'abord les données existantes")

    def handle(self, *args, **opts):
        if opts["reinitialiser"]:
            Bagage.objects.all().delete()
            Voyage.objects.all().delete()
            Pays.objects.all().delete()
            Utilisateur.objects.exclude(is_superuser=True).delete()
        if Voyage.objects.exists():
            self.stdout.write(self.style.WARNING("Des données existent déjà (utilisez --reinitialiser)."))
            return
        Parametres.charger()
        villes = {}
        for nom, code, devise, frais, tarif, pmax, dmin, dmax, fuseau, vs in PAYS:
            p, _ = Pays.objects.update_or_create(code=code, defaults=dict(
                nom=nom, devise=devise, frais_fixes=frais, tarif_kg=tarif, poids_max=pmax, delai_min=dmin, delai_max=dmax,
                fuseau=fuseau, objets_interdits=INTERDITS, documents_douane=DOCUMENTS, actif=True))
            for vn, lat, lng in vs:
                villes[vn], _ = Ville.objects.update_or_create(pays=p, nom=vn, defaults={"latitude": lat, "longitude": lng})

        def user(email, prenom, nom, role, **kw):
            u, cree = Utilisateur.objects.get_or_create(email=email, defaults=dict(
                first_name=prenom, last_name=nom, role=role, email_confirme=True, **kw))
            if cree:
                u.set_password("demo12345")
                u.save()
            return u

        admin = user("admin@demo.ca", "Nadia", "Gérante", "admin", is_staff=True, is_superuser=True)
        karim = user("karim@demo.ca", "Karim", "Benali", "transporteur", telephone="+1 514 555-0101")
        yacine = user("yacine@demo.ca", "Yacine", "Haddad", "transporteur", telephone="+1 514 555-0102")
        sara = user("sara@demo.ca", "Sara", "Bensalem", "client", telephone="+1 438 555-0199", pays_residence="Canada")
        omar = user("omar@demo.ca", "Omar", "Kaci", "client", telephone="+1 438 555-0123", pays_residence="Canada")

        now = timezone.now()
        h = lambda d, heure=18: (now + timedelta(days=d)).replace(hour=heure, minute=0, second=0, microsecond=0)
        lieu = "Entrepôt Talaouglid, 1234 rue Exemple, Montréal"

        def voyage(dep, arr, jours, cap, transporteur, moyen="avion", duree=16, escales=()):
            d = h(jours)
            v = Voyage.objects.create(ville_depart=villes[dep], ville_arrivee=villes[arr], depart=d,
                                         arrivee_prevue=d + timedelta(hours=duree), date_limite_depot=d - timedelta(hours=24),
                                         lieu_depot=lieu, heure_depot="de 10 h à 18 h", capacite_kg=cap,
                                         transporteur=transporteur, moyen=moyen)
            v.autres_villes.set([villes[e] for e in escales])
            return v

        en_cours = voyage("Montréal", "Paris", -1, 250, yacine, duree=30)
        alger = voyage("Montréal", "Alger", 12, 300, karim, escales=("Oran", "Constantine"))
        voyage("Montréal", "Oran", 19, 250, karim)
        voyage("Montréal", "Casablanca", 9, 200, yacine)
        voyage("Montréal", "Tunis", 16, 200, yacine)
        voyage("Toronto", "Paris", 6, 180, yacine, duree=9, escales=("Lyon", "Marseille"))
        voyage("Montréal", "Alger", 26, 300, karim)
        termine = voyage("Montréal", "Constantine", -12, 250, karim)

        def envoi(client, v, poids, desc, dest, statut=None):
            pays = v.pays_arrivee
            b = Bagage.objects.create(client=client, voyage=v, description=desc, poids=Decimal(poids),
                                      dest_nom=dest[0], dest_telephone=dest[1], dest_adresse=dest[2],
                                      frais_fixes=pays.frais_fixes, tarif_kg=pays.tarif_kg,
                                      prix=pays.calculer_prix(poids), devise=pays.devise)
            p = Paiement.objects.create(bagage=b, montant=b.prix, devise=b.devise)
            services.confirmer_paiement(p, reference=f"demo_{p.pk}")
            return b

        # Voyage Montréal → Alger (scénario 3)
        envoi(omar, alger, 18, "Valise : vêtements et cadeaux", ("Fatima Kaci", "+213 555 12 34 56", "12 rue Didouche Mourad, Alger"))
        # Voyage en cours vers Paris
        b1 = envoi(sara, en_cours, 22, "Valise de vêtements", ("Samia Bensalem", "+33 6 12 34 56 78", "5 rue de Rivoli, Paris"))
        b2 = envoi(omar, en_cours, 12, "Carton de livres", ("Ali Kaci", "+33 6 98 76 54 32", "18 bd Voltaire, Paris"))
        Voyage.objects.filter(pk=en_cours.pk).update(depart=now - timedelta(hours=5), date_limite_depot=now - timedelta(hours=29),
                                                    arrivee_prevue=now + timedelta(hours=20))
        en_cours.refresh_from_db()
        for b in (b1, b2):
            services.marquer_charge(en_cours, b.numero_suivi, yacine)
        services.demarrer_voyage(en_cours, yacine)
        Voyage.objects.filter(pk=en_cours.pk).update(demarre_le=now - timedelta(hours=5))
        Position.objects.create(voyage=en_cours, latitude=45.4706, longitude=-73.7408, lieu="Aéroport de Montréal-Trudeau",
                                envoyee_le=now - timedelta(hours=5), transporteur=yacine)
        Position.objects.create(voyage=en_cours, latitude=51.0, longitude=-35.0, lieu="Au-dessus de l'Atlantique",
                                envoyee_le=now - timedelta(minutes=40), transporteur=yacine)
        # Voyage terminé + livré
        Voyage.objects.filter(pk=termine.pk).update(depart=now - timedelta(days=12), date_limite_depot=now - timedelta(days=13),
                                                   arrivee_prevue=now - timedelta(days=11))
        termine.refresh_from_db()
        Voyage.objects.filter(pk=termine.pk).update(statut="planifie")
        b3 = Bagage.objects.create(client=sara, voyage=termine, description="Sac de voyage", poids=Decimal(10),
                                   dest_nom="Karima Bensalem", dest_telephone="+213 555 00 11 22", dest_adresse="Constantine",
                                   frais_fixes=Decimal(20), tarif_kg=Decimal(8), prix=Decimal(100), devise="CAD")
        p3 = Paiement.objects.create(bagage=b3, montant=b3.prix, devise="CAD")
        Voyage.objects.filter(pk=termine.pk).update(date_limite_depot=now + timedelta(days=1))
        termine.refresh_from_db()
        services.confirmer_paiement(p3, reference="demo")
        services.marquer_charge(termine, b3.numero_suivi, karim)
        services.demarrer_voyage(termine, karim)
        Position.objects.create(voyage=termine, latitude=36.2639, longitude=6.6208, lieu="Aéroport de Constantine", transporteur=karim)
        services.terminer_voyage(termine, karim)
        b3.refresh_from_db()
        services.valider_livraison(b3, b3.code_remise, None, karim)
        Voyage.objects.filter(pk=termine.pk).update(date_limite_depot=now - timedelta(days=13))

        AvisClient.objects.get_or_create(nom="Sara B.", ville="Montréal", texte="J'ai suivi la valise de ma mère jusqu'à Constantine sans appeler une seule fois. Parfait !")
        AvisClient.objects.get_or_create(nom="Omar K.", ville="Laval", texte="Réservation en 2 minutes, prix clair dès le simulateur.")
        AvisClient.objects.get_or_create(nom="Lina M.", ville="Québec", note=4, texte="Livraison rapide à Paris, le code de remise est rassurant.")

        self.stdout.write(self.style.SUCCESS(
            "Données de démo créées. Comptes (mot de passe : demo12345) :\n"
            "  admin@demo.ca (administrateur) · karim@demo.ca, yacine@demo.ca (transporteurs) · sara@demo.ca, omar@demo.ca (clients)\n"
            f"  Numéros de suivi : {b1.numero_suivi} (en transit), {b3.numero_suivi} (livré)"
        ))
