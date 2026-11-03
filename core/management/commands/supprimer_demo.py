"""
Supprime les données de démonstration : comptes @demo.ca, leurs voyages / envois / paiements / notifications,
et les avis clients de démo. Les pays et tarifs sont conservés (modifiables dans Gestion → Pays et tarifs).
Usage : python manage.py supprimer_demo   (ou SUPPRIMER_DEMO=true sur Render)
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from core.models import AvisClient, Bagage, MessageContact, Utilisateur, Voyage

AVIS_DEMO = ["Sara B.", "Omar K.", "Lina M."]


class Command(BaseCommand):
    help = "Supprime les comptes, voyages, envois et avis de démonstration (garde les pays et tarifs)."

    @transaction.atomic
    def handle(self, *args, **options):
        demo = Utilisateur.objects.filter(email__iendswith="@demo.ca")
        voyages = Voyage.objects.filter(transporteur__in=demo)
        bagages = Bagage.objects.filter(Q(client__in=demo) | Q(voyage__in=voyages))
        nb_b = bagages.count()
        bagages.delete()  # paiements, historique, incidents liés supprimés en cascade
        nb_v = voyages.count()
        voyages.delete()  # positions et incidents supprimés en cascade
        nb_a = AvisClient.objects.filter(nom__in=AVIS_DEMO).delete()[0]
        nb_u = demo.count()
        demo.delete()  # notifications et destinataires enregistrés supprimés en cascade
        MessageContact.objects.filter(courriel__iendswith="@demo.ca").delete()
        self.stdout.write(self.style.SUCCESS(
            f"Démo supprimée : {nb_u} comptes, {nb_v} voyages, {nb_b} envois, {nb_a} avis. Pays et tarifs conservés."
        ))
