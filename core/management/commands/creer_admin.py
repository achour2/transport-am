"""
Crée (ou met à jour) le compte administrateur à partir des variables d'environnement
DJANGO_ADMIN_EMAIL et DJANGO_ADMIN_PASSWORD. Utile sur un hébergeur sans accès console (Render gratuit).
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
        user, cree = Utilisateur.objects.get_or_create(email=email, defaults={"first_name": "Admin"})
        user.role = Utilisateur.Role.ADMIN
        user.is_staff = user.is_superuser = user.email_confirme = user.is_active = True
        user.set_password(mdp)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Administrateur {'créé' if cree else 'mis à jour'} : {email}"))
