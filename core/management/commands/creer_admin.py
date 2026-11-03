"""
Crée (ou met à jour) le compte administrateur à partir des variables d'environnement
DJANGO_ADMIN_EMAIL et DJANGO_ADMIN_PASSWORD. Utile sur un hébergeur sans accès console (Render gratuit).
Le compte n'est créé que s'il n'existe pas ; DJANGO_ADMIN_RESET=true force la remise du mot de passe.
"""
import os

from django.core.management.base import BaseCommand

from core.models import Utilisateur


class Command(BaseCommand):
    help = "Crée l'administrateur défini par DJANGO_ADMIN_EMAIL / DJANGO_ADMIN_PASSWORD."

    def handle(self, *args, **options):
        email = os.environ.get("DJANGO_ADMIN_EMAIL", "").strip().lower()
        mdp = os.environ.get("DJANGO_ADMIN_PASSWORD", "")
        if not email or not mdp:
            self.stdout.write("DJANGO_ADMIN_EMAIL / DJANGO_ADMIN_PASSWORD absents : aucun administrateur créé.")
            return
        user = Utilisateur.objects.filter(email__iexact=email).first()
        reinitialiser = os.environ.get("DJANGO_ADMIN_RESET", "").lower() in ("1", "true", "oui", "yes")
        if user and not reinitialiser:
            # Le compte existe : on ne touche pas à son mot de passe (il a pu être changé depuis le site)
            self.stdout.write(f"Administrateur déjà présent : {email} (mot de passe inchangé).")
            return
        cree = user is None
        if cree:
            user = Utilisateur(email=email, first_name="Admin")
        user.role = Utilisateur.Role.ADMIN
        user.is_staff = user.is_superuser = user.email_confirme = user.is_active = True
        user.set_password(mdp)
        user.save()
        self.stdout.write(self.style.SUCCESS(
            f"Administrateur {'créé' if cree else 'réinitialisé (DJANGO_ADMIN_RESET)'} : {email}"))
