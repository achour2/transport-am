from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from . import models


@admin.register(models.Utilisateur)
class UtilisateurAdmin(UserAdmin):
    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "role", "is_active"]
    list_filter = ["role", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    fieldsets = (
        (None, {"fields": ("email", "password", "role")}),
        ("Identité", {"fields": ("first_name", "last_name", "telephone", "pays_residence", "langue")}),
        ("Notifications", {"fields": ("notif_site", "notif_courriel", "notif_sms", "email_confirme")}),
        ("Droits", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "role", "password1", "password2")}),)


class VilleInline(admin.TabularInline):
    model = models.Ville
    extra = 1


@admin.register(models.Pays)
class PaysAdmin(admin.ModelAdmin):
    list_display = ["nom", "code", "frais_fixes", "tarif_kg", "poids_max", "actif"]
    inlines = [VilleInline]


@admin.register(models.Voyage)
class VoyageAdmin(admin.ModelAdmin):
    list_display = ["__str__", "transporteur", "capacite_kg", "statut"]
    list_filter = ["statut", "moyen"]


@admin.register(models.Bagage)
class BagageAdmin(admin.ModelAdmin):
    list_display = ["numero_suivi", "client", "voyage", "poids", "prix", "statut", "statut_paiement"]
    list_filter = ["statut", "statut_paiement"]
    search_fields = ["numero_suivi", "dest_nom", "client__email"]


for m in (models.Paiement, models.Notification, models.Position, models.Incident, models.EvenementBagage,
          models.MessageContact, models.AvisClient, models.Parametres, models.AbonnementSuivi, models.DestinataireEnregistre):
    admin.site.register(m)
