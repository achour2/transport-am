# Talaouglid — Plateforme de transport de bagages entre pays

Site web Django réalisé d’après le *Cahier des charges v1.0 (2 novembre 2026)*.
L’administrateur gère les pays, les tarifs et les voyages ; le transporteur met à jour sa position pendant le trajet ; le client réserve, paie et suit son bagage avec un numéro de suivi.

## Démarrage rapide (développement)

```bash
uv venv && uv pip install -r requirements.txt   # ou : python -m venv .venv && pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py donnees_demo          # pays, voyages, comptes et envois de démonstration
.venv/bin/python manage.py runserver
```

Ouvrir http://localhost:8000. Sans fichier `.env`, le projet tourne avec SQLite, affiche les courriels dans la console et utilise un **paiement simulé** (carte 4242 4242 4242 4242 acceptée, 4000 0000 0000 0002 refusée).

Comptes de démo (mot de passe `demo12345`) :

| Rôle | Courriel | Espace |
|---|---|---|
| Administrateur | admin@demo.ca | `/gestion` |
| Transporteurs | karim@demo.ca, yacine@demo.ca | `/transporteur` |
| Clients | sara@demo.ca, omar@demo.ca | `/client` |

## Ce qui est couvert

| Cahier des charges | Où |
|---|---|
| 4 rôles, chaque page vérifie le rôle | `core/decorators.py` |
| Données (section 4) | `core/models.py` |
| Règles de gestion (section 5) : prix figé, capacité / complet, date limite, pays désactivé au lieu de supprimé, annulations, code de remise, incidents | `core/services.py` |
| Espace public (6.1) : accueil, destinations, simulateur instantané (HTMX), suivi + carte Leaflet, inscription, FAQ / contact | `core/views/public.py` |
| Espace client (6.2) : tableau de bord, réservation en 4 étapes, paiement Stripe, reçu PDF, annulation, profil, suppression du compte (Loi 25) | `core/views/client.py` |
| Espace transporteur (6.3), conçu pour le téléphone : position GPS en 1 clic, saisie manuelle, chargement, démarrage, arrivée, livraison par code + photo, incidents | `core/views/transporteur.py` |
| Espace administrateur (6.4) : tableau de bord + carte + alertes, export Excel, pays, voyages (liste / calendrier / dupliquer / annuler), bagages, incidents, utilisateurs, paramètres | `core/views/gestion.py` |
| Notifications (section 8) dans le site + courriel ; SMS journalisé (V2) | `core/services.py` |
| Rappel de position toutes les 2 h, alerte admin après 4 h sans position, rappel 24 h avant la date limite de dépôt | `/taches/verifications/` (cron-job.org) ou `manage.py verifications` (cron) |
| API JSON (DRF) : `/api/suivi/<numéro>/`, `/api/pays/`, `/api/voyages-en-cours/` | `core/api.py` |
| FR / EN / AR (droite à gauche) | `locale/`, `scripts/traductions.py` |
| Dates stockées en UTC, affichées dans le fuseau du pays | filtre `tz` dans `core/templatetags/outils.py` |

## Tests des 8 scénarios

```bash
.venv/bin/python manage.py test core
```

25 tests : un ou plusieurs par scénario de la section 7 (ajout d’un pays, planification, réservation de Sara à 164 $, voyage avec rappels 2 h / alerte 4 h, suivi public, livraison avec code, incident retrouvé / perdu, annulations), plus les règles de gestion et les comptes.

## Mise en ligne rapide sur Render (gratuit)

1. Sur https://render.com, créez un compte avec **« Sign in with GitHub »**.
2. **New + → Blueprint**, choisissez le dépôt `transport-am` : Render lit `render.yaml` et prépare le site + la base PostgreSQL.
3. Remplissez `DJANGO_ADMIN_EMAIL` et `DJANGO_ADMIN_PASSWORD` (votre compte administrateur) ; les autres champs peuvent rester vides.
4. **Apply**. Après 3 à 5 minutes, le site est en ligne sur `https://talaouglid.onrender.com` (ou un nom proche).

`CHARGER_DEMO=true` ajoute les données de démonstration : passez-le à `false` dans **Environment** pour un vrai lancement.
Limites du plan gratuit : le site s’endort après 15 min sans visite (premier chargement ≈ 50 s), la base gratuite expire après 30 jours, les photos envoyées sont effacées à chaque redéploiement (configurer S3 pour les garder), et il n’y a pas de tâches planifiées (rappels 2 h).

## Mise en production (VPS OVHcloud)

1. Installer PostgreSQL 16, Redis et Nginx ; copier le projet dans `/srv/transbagages`.
2. `cp .env.example .env` puis remplir les valeurs (clé secrète, base, SMTP Brevo/SendGrid, clés Stripe, Redis).
3. `pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic && python manage.py createsuperuser`
4. Installer `deploiement/transbagages.service` (systemd) puis `deploiement/nginx.conf`, et programmer `python manage.py verifications` toutes les 10 min (cron).
5. HTTPS : `certbot --nginx -d votre-domaine` (Let’s Encrypt, obligatoire pour la géolocalisation).
6. Stripe : créer un webhook vers `https://votre-domaine/paiement/webhook/` (événement `checkout.session.completed`).
7. Sauvegarde nocturne conservée 30 jours : `deploiement/sauvegarde.sh` dans la crontab.

Les bibliothèques front (Bootstrap 5.3, Bootstrap Icons, HTMX, Leaflet) sont servies depuis `static/vendor/` : aucune dépendance à un CDN.

## Points encore à valider avec le client (section 11)

Liste réelle des pays / tarifs (modifiable dans **Gestion → Pays et tarifs**), devise de facturation (CAD par défaut), prix au volume, SMS en V1 (fournisseur à brancher dans `services.envoyer_sms`), ramassage à domicile, politique de remboursement en cas de perte, nom, logo et couleurs (nom et coordonnées modifiables dans **Gestion → Paramètres** ; couleurs dans `static/css/site.css`).
