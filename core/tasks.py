"""Tâches Celery (lancées par Celery Beat toutes les 10 minutes)."""
from celery import shared_task

from . import services


@shared_task
def verifications_periodiques():
    return services.verifications_periodiques()
