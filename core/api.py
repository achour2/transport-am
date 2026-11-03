"""API JSON (Django REST Framework) : carte du suivi et future application mobile."""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Bagage, Pays, Position, Voyage
from .securite import limite_requetes


class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = ["latitude", "longitude", "lieu", "envoyee_le"]


class PositionPubliqueSerializer(serializers.ModelSerializer):
    """Sans coordonnées : sécurité du transporteur."""

    class Meta:
        model = Position
        fields = ["lieu", "envoyee_le"]


class PaysSerializer(serializers.ModelSerializer):
    villes = serializers.SlugRelatedField(many=True, read_only=True, slug_field="nom")

    class Meta:
        model = Pays
        fields = ["code", "nom", "devise", "frais_fixes", "tarif_kg", "poids_max", "delai_min", "delai_max", "villes"]


def _point(ville):
    return {"nom": str(ville), "latitude": ville.latitude, "longitude": ville.longitude}


@api_view(["GET"])
@permission_classes([AllowAny])
@limite_requetes("api_suivi", nombre=30, secondes=60)
def suivi(request, numero):
    b = get_object_or_404(Bagage, numero_suivi=numero.upper(), statut_paiement__in=["paye", "rembourse"])
    v = b.voyage
    derniere = v.derniere_position if b.rang >= 2 else None
    return Response({
        "numero_suivi": b.numero_suivi,
        "statut": b.statut,
        "statut_libelle": b.get_statut_display(),
        "etape": b.rang,
        "destinataire": b.dest_nom_masque,
        "depart": _point(v.ville_depart),
        "arrivee": _point(v.ville_arrivee),
        "arrivee_prevue": v.arrivee_prevue,
        "derniere_position": PositionPubliqueSerializer(derniere).data if derniere else None,
        "historique": [{"date": e.cree_le, "statut": e.get_statut_display(), "message": e.message} for e in b.evenements.all()],
        "maintenant": timezone.now(),
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def pays(request):
    return Response(PaysSerializer(Pays.objects.filter(actif=True).prefetch_related("villes"), many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def voyages_en_cours(request):
    if request.user.role != "admin":
        return Response(status=403)
    data = []
    for v in Voyage.objects.filter(statut="en_cours").select_related("ville_depart", "ville_arrivee"):
        p = v.derniere_position
        data.append({
            "id": v.pk, "trajet": f"{v.ville_depart.nom} → {v.ville_arrivee.nom}",
            "depart": _point(v.ville_depart), "arrivee": _point(v.ville_arrivee),
            "derniere_position": PositionSerializer(p).data if p else None,
            "minutes_depuis_position": v.minutes_depuis_position,
        })
    return Response(data)
