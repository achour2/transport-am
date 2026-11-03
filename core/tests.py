"""
Tests des 8 scénarios d'utilisation (section 7 du cahier des charges)
+ règles de gestion (section 5). Lancer : python manage.py test
"""
from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core import services
from core.models import Bagage, Incident, Notification, Paiement, Pays, Position, Utilisateur, Ville, Voyage


@override_settings(STRIPE_SECRET_KEY="", PAIEMENT_EN_LIGNE=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class Base(TestCase):
    def setUp(self):
        self.admin = Utilisateur.objects.create_user("admin@t.ca", "x-Pass-1234", role="admin", first_name="Admin")
        self.karim = Utilisateur.objects.create_user("karim@t.ca", "x-Pass-1234", role="transporteur", first_name="Karim")
        self.sara = Utilisateur.objects.create_user("sara@t.ca", "x-Pass-1234", role="client", first_name="Sara",
                                                    email_confirme=True)
        self.canada = Pays.objects.create(nom="Canada", code="CA", devise="CAD", frais_fixes=20, tarif_kg=8, poids_max=30,
                                          fuseau="America/Toronto")
        self.algerie = Pays.objects.create(nom="Algérie", code="DZ", devise="CAD", frais_fixes=20, tarif_kg=8, poids_max=30,
                                           delai_min=5, delai_max=7, fuseau="Africa/Algiers")
        self.mtl = Ville.objects.create(pays=self.canada, nom="Montréal", latitude=45.5, longitude=-73.56)
        self.alger = Ville.objects.create(pays=self.algerie, nom="Alger", latitude=36.75, longitude=3.05)

    def creer_voyage(self, jours=10, capacite=300, **kw):
        d = timezone.now() + timedelta(days=jours)
        return Voyage.objects.create(ville_depart=self.mtl, ville_arrivee=self.alger, depart=d,
                                     arrivee_prevue=d + timedelta(hours=16), date_limite_depot=d - timedelta(hours=24),
                                     lieu_depot="Entrepôt", capacite_kg=capacite, transporteur=self.karim, **kw)

    def reserver(self, voyage, poids, client=None):
        b = services.creer_bagage(client or self.sara, voyage, {
            "description": "Valise", "poids": Decimal(poids), "dest_nom": "Mère de Sara",
            "dest_telephone": "+213 555", "dest_adresse": "Alger"})
        p = Paiement.objects.create(bagage=b, montant=b.prix, devise=b.devise)
        services.confirmer_paiement(p, "demo")
        b.refresh_from_db()
        return b


class Scenario1AjoutPays(Base):
    def test_admin_ajoute_la_tunisie(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("gestion_pays_ajouter"), {
            "nom": "Tunisie", "code": "tn", "devise": "CAD", "frais_fixes": "20", "tarif_kg": "8.50", "poids_max": "25",
            "delai_min": "6", "delai_max": "9", "fuseau": "Africa/Tunis", "objets_interdits": "Armes",
            "documents_douane": "Passeport", "actif": "on", "villes": "Tunis; 36.8; 10.18\nSfax"})
        self.assertRedirects(r, reverse("gestion_pays"))
        tn = Pays.objects.get(code="TN")
        self.assertTrue(tn.actif)
        self.assertEqual(set(tn.villes.values_list("nom", flat=True)), {"Tunis", "Sfax"})
        self.assertContains(self.client.get(reverse("destinations")), "Tunisie")
        self.assertContains(self.client.get(reverse("simulateur")), "Tunisie")
        self.assertEqual(tn.calculer_prix(15), Decimal("147.50"))  # grille tarifaire du cahier des charges

    def test_pays_utilise_est_desactive_et_non_supprime(self):
        self.creer_voyage()
        self.client.force_login(self.admin)
        self.client.post(reverse("gestion_pays_supprimer", args=[self.algerie.pk]))
        self.algerie.refresh_from_db()
        self.assertFalse(self.algerie.actif)

    def test_acces_reserve_admin(self):
        self.client.force_login(self.sara)
        self.assertEqual(self.client.get(reverse("gestion_pays")).status_code, 403)


class Scenario2PlanifierVoyage(Base):
    def donnees(self, **kw):
        d = {"ville_depart": self.mtl.pk, "ville_arrivee": self.alger.pk, "depart": "2030-12-15T18:00",
             "arrivee_prevue": "2030-12-16T10:00", "date_limite_depot": "2030-12-14T18:00", "lieu_depot": "Entrepôt",
             "capacite_kg": "300", "transporteur": self.karim.pk, "moyen": "avion"}
        d.update(kw)
        return d

    def test_admin_planifie_et_karim_est_notifie(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("gestion_voyage_creer"), self.donnees())
        self.assertRedirects(r, reverse("gestion_voyages"))
        v = Voyage.objects.get()
        self.assertTrue(Notification.objects.filter(destinataire=self.karim, message__startswith="Nouveau voyage assigné").exists())
        self.client.force_login(self.karim)
        self.assertContains(self.client.get(reverse("transporteur_voyages")), "Alger")
        self.assertIn(v, Voyage.reservables())

    def test_dates_incoherentes_refusees(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("gestion_voyage_creer"), self.donnees(arrivee_prevue="2030-12-14T10:00"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Voyage.objects.exists())

    def test_pays_identiques_ou_inactifs_refuses(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("gestion_voyage_creer"), self.donnees(ville_arrivee=self.mtl.pk))
        self.assertFalse(Voyage.objects.exists())

    def test_date_limite_par_defaut_24h(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("gestion_voyage_creer"), self.donnees(date_limite_depot=""))
        v = Voyage.objects.get()
        self.assertEqual(v.depart - v.date_limite_depot, timedelta(hours=24))


class Scenario3ReservationClient(Base):
    def test_sara_reserve_18_kg_vers_alger(self):
        voyage = self.creer_voyage(capacite=300)
        self.reserver(voyage, 18, client=Utilisateur.objects.create_user("autre@t.ca", "x", role="client"))  # 282 kg restants
        self.assertEqual(voyage.kilos_restants, Decimal("282"))

        # 1. Simulateur : 20 + 18 × 8 = 164 $
        r = self.client.get(reverse("simulateur"), {"pays": self.algerie.pk, "poids": "18"})
        self.assertContains(r, "164")

        # 2-5. Réservation en 4 étapes puis paiement
        self.client.force_login(self.sara)
        self.client.post(reverse("client_envoi_nouveau"), {"pays": self.algerie.pk, "voyage": voyage.pk})
        self.client.post(reverse("client_envoi_etape", args=[2]), {"description": "Valise", "poids": "18", "valeur_declaree": "200"})
        self.client.post(reverse("client_envoi_etape", args=[3]), {"dest_nom": "Mère de Sara", "dest_telephone": "+213 555 12",
                                                                   "dest_adresse": "Alger centre"})
        r = self.client.post(reverse("client_envoi_etape", args=[4]), {"accepte": "on"})
        bagage = Bagage.objects.get(client=self.sara)
        self.assertRedirects(r, reverse("client_payer", args=[bagage.numero_suivi]))
        self.assertEqual(bagage.prix, Decimal("164.00"))
        mail.outbox.clear()
        self.client.post(reverse("client_payer", args=[bagage.numero_suivi]), {"carte": "4242424242424242"})

        bagage.refresh_from_db()
        self.assertEqual(bagage.statut_paiement, "paye")
        self.assertRegex(bagage.numero_suivi, r"^BG-[A-Z0-9]{8}$")
        self.assertEqual(len(bagage.code_remise), 6)
        self.assertEqual(voyage.kilos_restants, Decimal("264"))
        courriel = mail.outbox[0]
        self.assertIn(bagage.numero_suivi, courriel.body)
        self.assertIn("Entrepôt", courriel.body)
        self.assertEqual(self.client.get(reverse("client_recu", args=[bagage.numero_suivi]))["Content-Type"], "application/pdf")

    def test_poids_superieur_au_maximum_refuse(self):
        with self.assertRaises(services.ErreurMetier):
            services.calculer_prix(self.algerie, 31)

    def test_capacite_et_complet(self):
        voyage = self.creer_voyage(capacite=20)
        self.reserver(voyage, 20)
        self.assertTrue(voyage.est_complet)
        self.assertFalse(voyage.reservations_ouvertes)
        with self.assertRaises(services.ErreurMetier):
            services.creer_bagage(self.sara, voyage, {"description": "x", "poids": Decimal(1), "dest_nom": "a",
                                                      "dest_telephone": "1", "dest_adresse": "b"})

    def test_reservations_fermees_apres_date_limite(self):
        voyage = self.creer_voyage(jours=0.5)  # date limite déjà dépassée
        self.assertFalse(voyage.reservations_ouvertes)

    def test_prix_fige_apres_changement_de_tarif(self):
        voyage = self.creer_voyage()
        b = self.reserver(voyage, 10)
        self.algerie.tarif_kg = 12
        self.algerie.save()
        b.refresh_from_db()
        self.assertEqual(b.prix, Decimal("100.00"))

    def test_carte_refusee(self):
        voyage = self.creer_voyage()
        b = services.creer_bagage(self.sara, voyage, {"description": "x", "poids": Decimal(5), "dest_nom": "a",
                                                      "dest_telephone": "1", "dest_adresse": "b"})
        self.client.force_login(self.sara)
        self.client.post(reverse("client_payer", args=[b.numero_suivi]), {"carte": "4000000000000002"})
        b.refresh_from_db()
        self.assertEqual(b.statut_paiement, "echoue")
        self.assertEqual(voyage.kilos_reserves, 0)


class Scenario4Transporteur(Base):
    def test_voyage_complet_avec_rappels(self):
        voyage = self.creer_voyage()
        b = self.reserver(voyage, 18)
        self.client.force_login(self.karim)
        url = reverse("transporteur_voyage", args=[voyage.pk])
        # 1. Marquer chargé
        self.client.post(url, {"action": "charger", "numero": b.numero_suivi.lower()})
        b.refresh_from_db()
        self.assertEqual(b.statut, "charge")
        # 2. Démarrer : en transit + client notifié
        self.client.post(url, {"action": "demarrer"})
        b.refresh_from_db()
        self.assertEqual(b.statut, "en_transit")
        self.assertTrue(Notification.objects.filter(destinataire=self.sara, message__contains="en transit").exists())
        # 3. Position depuis l'aéroport
        self.client.post(reverse("transporteur_position"), {"voyage": voyage.pk, "latitude": "45.47", "longitude": "-73.74",
                                                            "lieu": "Aéroport de Montréal"})
        self.assertEqual(Position.objects.count(), 1)
        # 4. Deux heures plus tard : rappel au transporteur
        t0 = timezone.now()
        r = services.verifications_periodiques(t0 + timedelta(hours=2, minutes=1))
        self.assertEqual(r["rappels"], 1)
        self.assertTrue(Notification.objects.filter(destinataire=self.karim, message__contains="mettre à jour votre position").exists())
        # 5. Rien pendant 4 h : alerte admin (une seule fois)
        r = services.verifications_periodiques(t0 + timedelta(hours=4, minutes=1))
        self.assertEqual(r["alertes"], 1)
        self.assertTrue(Notification.objects.filter(destinataire=self.admin, message__startswith="Aucune position").exists())
        self.assertEqual(services.verifications_periodiques(t0 + timedelta(hours=4, minutes=20))["alertes"], 0)
        # 6. Arrivé
        self.client.post(url, {"action": "arrive"})
        b.refresh_from_db()
        voyage.refresh_from_db()
        self.assertEqual(b.statut, "arrive")
        self.assertEqual(voyage.statut, "termine")
        self.assertContains(self.client.get(reverse("suivi_detail", args=[b.numero_suivi])), "Arrivé à destination")

    def test_autre_transporteur_refuse(self):
        voyage = self.creer_voyage()
        autre = Utilisateur.objects.create_user("t2@t.ca", "x", role="transporteur")
        self.client.force_login(autre)
        self.assertEqual(self.client.get(reverse("transporteur_voyage", args=[voyage.pk])).status_code, 404)


class Scenario5Suivi(Base):
    def test_suivi_public(self):
        voyage = self.creer_voyage()
        b = self.reserver(voyage, 18)
        services.marquer_charge(voyage, b.numero_suivi, self.karim)
        services.demarrer_voyage(voyage, self.karim)
        services.enregistrer_position(voyage, self.karim, 45.4, -73.7, "Aéroport de Montréal")
        r = self.client.get(reverse("suivi"), {"numero": b.numero_suivi})
        self.assertRedirects(r, reverse("suivi_detail", args=[b.numero_suivi]))
        r = self.client.get(reverse("suivi_detail", args=[b.numero_suivi]))
        self.assertContains(r, "En transit")
        self.assertContains(r, "Aéroport de Montréal")
        self.assertContains(r, "M*** S.")  # nom du destinataire masqué
        self.assertNotContains(r, "Mère de Sara")
        self.assertNotContains(r, b.code_remise)
        api = self.client.get(reverse("api_suivi", args=[b.numero_suivi])).json()
        self.assertEqual(api["etape"], 2)
        self.assertEqual(len(api["positions"]), 1)

    def test_numero_inconnu(self):
        r = self.client.get(reverse("suivi"), {"numero": "BG-AAAAAAAA"})
        self.assertContains(r, "Aucun bagage")

    def test_abonnement_courriel(self):
        voyage = self.creer_voyage()
        b = self.reserver(voyage, 5)
        self.client.post(reverse("suivi_detail", args=[b.numero_suivi]), {"courriel": "maman@t.dz"})
        mail.outbox.clear()
        services.marquer_charge(voyage, b.numero_suivi, self.karim)
        self.assertTrue(any("maman@t.dz" in m.to for m in mail.outbox))


class Scenario6Livraison(Base):
    def test_livraison_avec_code(self):
        voyage = self.creer_voyage()
        b = self.reserver(voyage, 18)
        services.marquer_charge(voyage, b.numero_suivi, self.karim)
        services.demarrer_voyage(voyage, self.karim)
        services.terminer_voyage(voyage, self.karim)
        self.client.force_login(self.karim)
        url = reverse("transporteur_livraison", args=[b.numero_suivi])
        self.client.post(url, {"code": "000000" if b.code_remise != "000000" else "111111"})
        b.refresh_from_db()
        self.assertEqual(b.statut, "arrive")  # mauvais code refusé
        self.client.post(url, {"code": b.code_remise})
        b.refresh_from_db()
        self.assertEqual(b.statut, "livre")
        self.assertTrue(Notification.objects.filter(destinataire=self.sara, message__contains="livré").exists())


class Scenario7Incident(Base):
    def test_bagage_introuvable_puis_retrouve_ou_perdu(self):
        voyage = self.creer_voyage()
        b = self.reserver(voyage, 18)
        b2 = self.reserver(voyage, 10)
        for x in (b, b2):
            services.marquer_charge(voyage, x.numero_suivi, self.karim)
        services.demarrer_voyage(voyage, self.karim)
        self.client.force_login(self.karim)
        self.client.post(reverse("transporteur_voyage", args=[voyage.pk]),
                         {"action": "incident", "type": "introuvable", "numero": b.numero_suivi, "commentaire": "Manque au déchargement"})
        b.refresh_from_db()
        self.assertEqual(b.statut, "incident")
        self.assertTrue(Notification.objects.filter(destinataire=self.admin, message__startswith="Incident signalé").exists())
        self.assertTrue(Notification.objects.filter(destinataire=self.sara, message__contains="recherche est en cours").exists())
        # Retrouvé : le suivi reprend
        inc = Incident.objects.get(bagage=b)
        self.client.force_login(self.admin)
        self.client.post(reverse("gestion_incidents"), {"pk": inc.pk, "etat": "retrouve"})
        b.refresh_from_db()
        self.assertEqual(b.statut, "en_transit")
        # Perdu : remboursement
        inc2 = services.signaler_incident(voyage, self.karim, "introuvable", "", b2)
        services.traiter_incident(inc2, "perdu", self.admin)
        b2.refresh_from_db()
        self.assertEqual((b2.statut, b2.statut_paiement), ("perdu", "rembourse"))
        self.assertGreaterEqual(b.evenements.count(), 4)  # chaque étape est datée


class Scenario8Annulation(Base):
    def test_client_annule_avant_date_limite(self):
        voyage = self.creer_voyage()
        b = self.reserver(voyage, 18)
        self.client.force_login(self.sara)
        self.client.post(reverse("client_annuler", args=[b.numero_suivi]))
        b.refresh_from_db()
        self.assertEqual((b.statut, b.statut_paiement), ("annule", "rembourse"))
        self.assertEqual(voyage.kilos_restants, Decimal("300"))

    def test_annulation_impossible_apres_depot(self):
        voyage = self.creer_voyage()
        b = self.reserver(voyage, 18)
        services.changer_statut(b, Bagage.Statut.DEPOSE, self.admin)
        self.client.force_login(self.sara)
        self.client.post(reverse("client_annuler", args=[b.numero_suivi]))
        b.refresh_from_db()
        self.assertEqual(b.statut_paiement, "paye")

    def test_admin_annule_voyage_client_choisit(self):
        voyage = self.creer_voyage()
        autre = self.creer_voyage(jours=20)
        b = self.reserver(voyage, 18)
        b2 = self.reserver(voyage, 5)
        self.client.force_login(self.admin)
        self.client.post(reverse("gestion_voyage_annuler", args=[voyage.pk]))
        b.refresh_from_db()
        self.assertTrue(b.choix_requis)
        self.client.force_login(self.sara)
        self.client.post(reverse("client_choix", args=[b.numero_suivi]), {"choix": "deplacer", "voyage": autre.pk})
        b.refresh_from_db()
        self.assertEqual(b.voyage, autre)
        self.assertEqual(autre.kilos_reserves, Decimal("18"))
        self.client.post(reverse("client_choix", args=[b2.numero_suivi]), {"choix": "rembourser"})
        b2.refresh_from_db()
        self.assertEqual(b2.statut_paiement, "rembourse")


class Comptes(Base):
    def test_inscription_et_redirection_par_role(self):
        r = self.client.post(reverse("inscription"), {
            "first_name": "Lina", "last_name": "M", "email": "lina@t.ca", "telephone": "514", "pays_residence": "Canada",
            "password1": "Tres-Secret-2026", "password2": "Tres-Secret-2026", "accepte_conditions": "on"})
        self.assertRedirects(r, reverse("redirection_role"), fetch_redirect_response=False)
        self.assertTrue(any("confirmer" in m.body for m in mail.outbox))
        self.client.logout()
        r = self.client.post(reverse("connexion"), {"username": "karim@t.ca", "password": "x-Pass-1234"}, follow=True)
        self.assertEqual(r.redirect_chain[-1][0], reverse("transporteur_voyages"))

    def test_suppression_compte_loi25(self):
        self.client.force_login(self.sara)
        self.client.post(reverse("client_supprimer_compte"))
        self.assertFalse(Utilisateur.objects.filter(email="sara@t.ca").exists())


class EnvoiComptoir(Base):
    """Le client paie en espèces : l'admin crée l'envoi (et le compte) pour qu'il puisse suivre son bagage."""

    def donnees(self, voyage, **kw):
        d = {"courriel": "lina@t.ca", "prenom": "Lina", "nom": "Mansouri", "telephone": "+1 514 555 0000",
             "voyage": voyage.pk, "description": "Valise", "poids": "15", "valeur_declaree": "0",
             "dest_nom": "Yasmine M", "dest_telephone": "+213 555", "dest_adresse": "Oran", "mode": "especes", "depose": "on"}
        d.update(kw)
        return d

    def test_nouveau_client_compte_cree_et_suivi(self):
        voyage = self.creer_voyage()
        self.client.force_login(self.admin)
        mail.outbox.clear()
        r = self.client.post(reverse("gestion_envoi_comptoir"), self.donnees(voyage))
        b = Bagage.objects.get()
        self.assertRedirects(r, reverse("gestion_bagage", args=[b.numero_suivi]) + "?nouveau=1")
        lina = Utilisateur.objects.get(email="lina@t.ca")
        self.assertEqual((b.client, b.statut, b.statut_paiement, b.prix), (lina, "depose", "paye", Decimal("140.00")))
        p = b.paiements.get()
        self.assertEqual((p.mode, p.encaisse_par), ("especes", self.admin))
        self.assertEqual(voyage.kilos_restants, Decimal("285"))
        self.assertTrue(any("mot-de-passe/nouveau" in m.body and "lina@t.ca" in m.to for m in mail.outbox))
        self.assertEqual(self.client.get(reverse("gestion_recu", args=[b.numero_suivi]))["Content-Type"], "application/pdf")
        # Le client voit son envoi dans son espace
        self.client.force_login(lina)
        self.assertContains(self.client.get(reverse("client_tableau")), b.numero_suivi)

    def test_client_existant_et_sans_courriel(self):
        voyage = self.creer_voyage()
        self.client.force_login(self.admin)
        self.client.post(reverse("gestion_envoi_comptoir"), self.donnees(voyage, courriel="SARA@t.ca"))
        self.assertEqual(Bagage.objects.get().client, self.sara)
        self.client.post(reverse("gestion_envoi_comptoir"), self.donnees(voyage, courriel=""))
        sans = Bagage.objects.get(client__isnull=True)
        self.assertEqual(self.client.get(reverse("suivi_detail", args=[sans.numero_suivi])).status_code, 200)

    def test_remboursement_especes_sans_stripe(self):
        voyage = self.creer_voyage()
        self.client.force_login(self.admin)
        self.client.post(reverse("gestion_envoi_comptoir"), self.donnees(voyage, depose=""))
        b = Bagage.objects.get()
        services.rembourser(b, self.admin)
        self.assertTrue(b.evenements.filter(message__contains="au comptoir").exists())

    def test_reserve_admin(self):
        self.client.force_login(self.sara)
        self.assertEqual(self.client.get(reverse("gestion_envoi_comptoir")).status_code, 403)


class SuppressionDemo(TestCase):
    def test_supprimer_demo(self):
        from django.core.management import call_command

        call_command("donnees_demo", verbosity=0)
        reel = Utilisateur.objects.create_user("vrai@client.ca", "x", role="client")
        self.assertTrue(Voyage.objects.exists())
        call_command("supprimer_demo", verbosity=0)
        self.assertFalse(Utilisateur.objects.filter(email__endswith="@demo.ca").exists())
        self.assertFalse(Voyage.objects.exists())
        self.assertFalse(Bagage.objects.exists())
        self.assertTrue(Utilisateur.objects.filter(pk=reel.pk).exists())
        self.assertTrue(Pays.objects.filter(code="DZ").exists())


@override_settings(PAIEMENT_EN_LIGNE=False)
class ReservationPaiementComptoir(Base):
    """Paiement en ligne désactivé : le client réserve en ligne, l'admin encaisse au comptoir."""

    def reserver_en_ligne(self, voyage, poids="18"):
        self.client.force_login(self.sara)
        self.client.post(reverse("client_envoi_nouveau"), {"pays": self.algerie.pk, "voyage": voyage.pk})
        self.client.post(reverse("client_envoi_etape", args=[2]), {"description": "Valise", "poids": poids, "valeur_declaree": "0"})
        self.client.post(reverse("client_envoi_etape", args=[3]), {"dest_nom": "Mère", "dest_telephone": "+213", "dest_adresse": "Alger"})
        return self.client.post(reverse("client_envoi_etape", args=[4]), {"accepte": "on"})

    def test_reservation_bloque_les_kilos_puis_admin_encaisse(self):
        voyage = self.creer_voyage(capacite=300)
        r = self.reserver_en_ligne(voyage)
        b = Bagage.objects.get()
        self.assertRedirects(r, reverse("client_envoi", args=[b.numero_suivi]))
        self.assertTrue(b.a_encaisser)
        self.assertEqual(voyage.kilos_restants, Decimal("282"))  # kilos bloqués
        self.assertContains(self.client.get(reverse("client_envoi", args=[b.numero_suivi])), "payer au point de dépôt")
        # La carte de test ne peut plus être utilisée
        self.client.post(reverse("client_payer", args=[b.numero_suivi]), {"carte": "4242424242424242"})
        b.refresh_from_db()
        self.assertEqual(b.statut_paiement, "en_attente")
        self.assertFalse(Paiement.objects.exists())
        # L'admin encaisse en espèces
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("gestion_bagages") + "?a_encaisser=1"), b.numero_suivi)
        self.client.post(reverse("gestion_bagage", args=[b.numero_suivi]), {"action": "encaisser", "mode": "especes", "depose": "on"})
        b.refresh_from_db()
        self.assertEqual((b.statut_paiement, b.statut), ("paye", "depose"))
        self.assertEqual(b.paiements.get().mode, "especes")
        self.assertEqual(voyage.kilos_restants, Decimal("282"))  # pas compté deux fois
        self.assertEqual(self.client.get(reverse("suivi_detail", args=[b.numero_suivi])).status_code, 200)

    def test_capacite_tient_compte_des_reservations(self):
        voyage = self.creer_voyage(capacite=20)
        self.reserver_en_ligne(voyage, "18")
        with self.assertRaises(services.ErreurMetier):
            services.creer_bagage(self.sara, voyage, {"description": "x", "poids": Decimal(5), "dest_nom": "a",
                                                      "dest_telephone": "1", "dest_adresse": "b"})

    def test_annulation_et_expiration_liberent_les_kilos(self):
        voyage = self.creer_voyage(capacite=100)
        self.reserver_en_ligne(voyage, "10")
        b = Bagage.objects.get()
        self.client.post(reverse("client_annuler", args=[b.numero_suivi]))
        b.refresh_from_db()
        self.assertEqual(b.statut, "annule")
        self.assertEqual(voyage.kilos_restants, Decimal("100"))
        # Expiration à la date limite de dépôt
        self.reserver_en_ligne(voyage, "10")
        b2 = Bagage.objects.exclude(pk=b.pk).get()
        r = services.verifications_periodiques(voyage.date_limite_depot + timedelta(minutes=1))
        b2.refresh_from_db()
        self.assertEqual((r.get("expirees"), b2.statut), (1, "annule"))


class VoyagePlusieursVilles(Base):
    """Un voyage peut desservir 1 à N villes du pays d'arrivée."""

    def setUp(self):
        super().setUp()
        self.oran = Ville.objects.create(pays=self.algerie, nom="Oran", latitude=35.7, longitude=-0.63)
        self.paris = Ville.objects.create(pays=Pays.objects.create(nom="France", code="FR", devise="CAD", frais_fixes=15,
                                                                  tarif_kg=7, poids_max=30, fuseau="Europe/Paris"), nom="Paris")

    def test_admin_ajoute_des_escales_du_meme_pays(self):
        self.client.force_login(self.admin)
        base = {"ville_depart": self.mtl.pk, "ville_arrivee": self.alger.pk, "depart": "2030-12-15T18:00",
                "arrivee_prevue": "2030-12-16T10:00", "lieu_depot": "Entrepôt", "capacite_kg": "300",
                "transporteur": self.karim.pk, "moyen": "avion"}
        r = self.client.post(reverse("gestion_voyage_creer"), {**base, "autres_villes": [self.paris.pk]})
        self.assertEqual(r.status_code, 200)  # Paris n'est pas en Algérie : refusé
        self.client.post(reverse("gestion_voyage_creer"), {**base, "autres_villes": [self.oran.pk]})
        v = Voyage.objects.get()
        self.assertEqual([x.nom for x in v.villes_desservies], ["Alger", "Oran"])
        self.assertEqual(v.destinations_texte, "Alger, Oran")

    def test_client_reserve_pour_oran(self):
        voyage = self.creer_voyage()
        voyage.autres_villes.add(self.oran)
        self.client.force_login(self.sara)
        r = self.client.get(reverse("client_envoi_nouveau"), {"pays": self.algerie.pk, "ville": self.oran.pk})
        self.assertContains(r, "Alger, Oran")
        self.client.post(reverse("client_envoi_nouveau"), {"pays": self.algerie.pk, "ville": self.oran.pk, "voyage": voyage.pk})
        self.client.post(reverse("client_envoi_etape", args=[2]), {"description": "Valise", "poids": "10", "valeur_declaree": "0"})
        self.client.post(reverse("client_envoi_etape", args=[3]), {"dest_nom": "A B", "dest_telephone": "1", "dest_adresse": "Oran"})
        self.client.post(reverse("client_envoi_etape", args=[4]), {"accepte": "on"})
        b = Bagage.objects.get()
        self.assertEqual(b.ville_livraison, self.oran)
        # Un voyage qui ne dessert pas Oran n'apparaît pas pour Oran
        autre = self.creer_voyage(jours=20)
        r = self.client.get(reverse("simulateur"), {"pays": self.algerie.pk, "ville": self.oran.pk, "poids": "5"})
        self.assertNotIn(autre, r.context["resultat"]["voyages"])
        self.assertIn(voyage, r.context["resultat"]["voyages"])

    def test_ville_non_desservie_refusee(self):
        voyage = self.creer_voyage()
        with self.assertRaises(services.ErreurMetier):
            services.creer_bagage(self.sara, voyage, {"description": "x", "poids": Decimal(5), "dest_nom": "a",
                                                      "dest_telephone": "1", "dest_adresse": "b", "ville_destination": self.oran})


@override_settings(VERIFICATIONS_JETON="secret-123")
class TachesPlanifiees(TestCase):
    def test_jeton_obligatoire(self):
        self.assertEqual(self.client.get("/taches/verifications/").status_code, 403)
        self.assertEqual(self.client.get("/taches/verifications/", HTTP_X_JETON="faux").status_code, 403)
        r = self.client.get("/taches/verifications/", HTTP_X_JETON="secret-123")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    @override_settings(VERIFICATIONS_JETON="")
    def test_sans_jeton_configure_tout_est_refuse(self):
        self.assertEqual(self.client.get("/taches/verifications/?jeton=").status_code, 403)

    def test_creer_admin_ne_change_pas_le_mot_de_passe(self):
        import os
        from django.core.management import call_command

        os.environ.update(DJANGO_ADMIN_EMAIL="chef@t.ca", DJANGO_ADMIN_PASSWORD="Premier-Mdp-123")
        try:
            call_command("creer_admin", verbosity=0)
            u = Utilisateur.objects.get(email="chef@t.ca")
            u.set_password("Change-Depuis-Le-Site-9")
            u.save()
            call_command("creer_admin", verbosity=0)
            u.refresh_from_db()
            self.assertTrue(u.check_password("Change-Depuis-Le-Site-9"))
        finally:
            for k in ("DJANGO_ADMIN_EMAIL", "DJANGO_ADMIN_PASSWORD"):
                os.environ.pop(k, None)
