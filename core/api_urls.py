from django.urls import path

from . import api

urlpatterns = [
    path("suivi/<str:numero>/", api.suivi, name="api_suivi"),
    path("pays/", api.pays, name="api_pays"),
    path("voyages-en-cours/", api.voyages_en_cours, name="api_voyages_en_cours"),
]
