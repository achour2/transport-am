"""Alternative à Celery : `python manage.py verifications` (à lancer par cron toutes les 10 min)."""
from django.core.management.base import BaseCommand

from core.services import verifications_periodiques


class Command(BaseCommand):
    help = "Envoie les rappels de position, les alertes sans position et les rappels de dépôt."

    def handle(self, *args, **options):
        r = verifications_periodiques()
        self.stdout.write(self.style.SUCCESS(
            f"Rappels de position : {r['rappels']} · Alertes admin : {r['alertes']} · Rappels de dépôt : {r['rappels_depot']}"
        ))
